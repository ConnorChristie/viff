# Copyright 2009 VIFF Development Team.
#
# This file is part of VIFF, the Virtual Ideal Functionality Framework.
#
# VIFF is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License (LGPL) as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# VIFF is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with VIFF. If not, see <http://www.gnu.org/licenses/>.

"""MPC implementation of AES (Rijndael). This module can be used to
securely compute a secret shared AES encrypted ciphertext of a
(possibly) secret shared plaintext with a (possibly) secret shared
key. The inputs have to be given either as a list of shares over GF256
(byte-wise) or as a string. The runtime has to be able to handle
shares over GF256. Decryption is not implemented yet.

The implementation is based on the fact that AES has arithmetic
properties which makes its computation by arithmetic circuits
relatively fast."""

import operator
import time

from viff.math.field import GF256
from viff.runtime import Share, gather_shares
from viff.utils.matrix import Matrix


def bit_decompose(share, use_lin_comb=True):
    """Bit decomposition for GF256 shares."""

    assert isinstance(share, Share) and share.field == GF256, \
        "Parameter must be GF256 share."

    r_bits = share.runtime.prss_share_random_multi(GF256, 8, binary=True)

    if use_lin_comb:
        r = share.runtime.lin_comb([2 ** i for i in range(8)], r_bits)
    else:
        r = sum([r_bits[i] * 2 ** i for i in range(8)])

    c = share.runtime.open(share + r)
    c_bits = [Share(share.runtime, GF256) for i in range(8)]

    def decompose(byte, bits):
        value = byte.value

        for i in range(8):
            c_bits[i].callback(GF256(value & 1))
            value >>= 1

    c.addCallback(decompose, c_bits)

    return [c_bits[i] + r_bits[i] for i in range(8)]


class AES:
    """AES instantiation.

    This class is used together with a :class:`~viff.runtime.Runtime`
    object::

        aes = AES(runtime, 192)
        cleartext = [Share(runtime, GF256, GF256(0)) for i in range(128/8)]
        key = [runtime.prss_share_random(GF256) for i in range(192/8)]
        ciphertext = aes.encrypt("abcdefghijklmnop", key)
        ciphertext = aes.encrypt(cleartext, "keykeykeykeykeykeykeykey")
        ciphertext = aes.encrypt(cleartext, key)

    In every case *ciphertext* will be a list of shares over GF256.
    """

    def __init__(self, runtime, key_size, block_size=128,
                 use_exponentiation=False, quiet=False):
        """Initialize Rijndael.

        AES(runtime, key_size, block_size), whereas key size and block
        size must be given in bits. Block size defaults to 128."""

        assert key_size in [128, 192, 256], \
            "Key size must be 128, 192 or 256"
        assert block_size in [128, 192, 256], \
            "Block size be 128, 192 or 256"

        self.n_k = key_size / 32
        self.n_b = block_size / 32
        self.rounds = max(self.n_k, self.n_b) + 6
        self.runtime = runtime

        if use_exponentiation is not False:
            if (isinstance(use_exponentiation, int) and
                    use_exponentiation < len(AES.exponentiation_variants)):
                use_exponentiation = \
                    AES.exponentiation_variants[use_exponentiation]
            elif use_exponentiation not in AES.exponentation_variants:
                use_exponentiation = "shortest_sequential_chain"

            if not quiet:
                print "Use %s for inversion by exponentiation." % \
                      use_exponentiation

            if use_exponentiation == "standard_square_and_multiply":
                self.invert = lambda byte: byte ** 254
            elif use_exponentiation == "shortest_chain_with_least_rounds":
                self.invert = self.invert_by_exponentiation_with_less_rounds
            elif use_exponentiation == "chain_with_least_rounds":
                self.invert = self.invert_by_exponentiation_with_least_rounds
            elif use_exponentiation == "masked":
                self.invert = self.invert_by_masked_exponentiation
            elif use_exponentiation == "masked_online":
                self.invert = self.invert_by_masked_exponentiation_online
            else:
                self.invert = self.invert_by_exponentiation
        else:
            self.invert = self.invert_by_masking

            if not quiet:
                print "Use inversion by masking."

    exponentiation_variants = ["standard_square_and_multiply",
                               "shortest_sequential_chain",
                               "shortest_chain_with_least_rounds",
                               "chain_with_least_rounds",
                               "masked",
                               "masked_online"]

    def invert_by_masking(self, byte):
        bits = bit_decompose(byte)

        for j in range(len(bits)):
            bits[j].addCallback(lambda x: 1 - x)
        #            bits[j] = 1 - bits[j]

        while len(bits) > 1:
            bits.append(bits.pop(0) * bits.pop(0))

        # b == 1 if byte is 0, b == 0 else
        b = bits[0]

        r = Share(self.runtime, GF256)
        c = Share(self.runtime, GF256)

        def get_masked_byte(c_opened, r_related, c, r, byte):
            if c_opened == 0:
                r_trial = self.runtime.prss_share_random(GF256)
                c_trial = self.runtime.open((byte + b) * r_trial)
                self.runtime.schedule_callback(c_trial, get_masked_byte,
                                               r_trial, c, r, byte)
            else:
                r_related.addCallback(r.callback)
                c.callback(~c_opened)

        get_masked_byte(0, None, c, r, byte)

        # necessary to avoid communication in multiplication
        # was: return c * r - b
        result = gather_shares([c, r, b])
        result.addCallback(lambda (c, r, b): c * r - b)
        return result

    def invert_by_masked_exponentiation(self, byte):
        def add_and_multiply(masked_byte, random_powers, prep):
            masked_powers = self.runtime.powerchain(masked_byte, 7)
            byte_powers = map(operator.add, masked_powers, random_powers)[1:]
            if prep:
                byte_powers = [Share(self.runtime, GF256, value)
                               for value in byte_powers]
            while len(byte_powers) > 1:
                byte_powers.append(byte_powers.pop(0) * byte_powers.pop(0))
            return byte_powers[0]

        random_powers, prep = self.runtime.prss_powerchain()
        masked_byte = self.runtime.open(byte + random_powers[0])
        return self.runtime.schedule_callback(
            masked_byte, add_and_multiply, random_powers, prep)

    # constants for efficient computation of x^2, x^4, x^8 etc.
    powers_of_two = [[GF256(2 ** j) ** (2 ** i) for j in range(8)] for i in range(8)]

    def invert_by_masked_exponentiation_online(self, byte):
        bits = bit_decompose(byte)
        byte_powers = []

        for i in range(1, 8):
            byte_powers.append(self.runtime.lin_comb(AES.powers_of_two[i], bits))

        while len(byte_powers) > 1:
            byte_powers.append(byte_powers.pop(0) * byte_powers.pop(0))

        return byte_powers[0]

    def invert_by_exponentiation(self, byte):
        byte_2 = byte * byte
        byte_3 = byte_2 * byte
        byte_6 = byte_3 * byte_3
        byte_12 = byte_6 * byte_6
        byte_15 = byte_12 * byte_3
        byte_30 = byte_15 * byte_15
        byte_60 = byte_30 * byte_30
        byte_63 = byte_60 * byte_3
        byte_126 = byte_63 * byte_63
        byte_252 = byte_126 * byte_126
        byte_254 = byte_252 * byte_2
        return byte_254

    def invert_by_exponentiation_with_less_rounds(self, byte):
        byte_2 = byte * byte
        byte_4 = byte_2 * byte_2
        byte_8 = byte_4 * byte_4
        byte_9 = byte_8 * byte
        byte_18 = byte_9 * byte_9
        byte_19 = byte_18 * byte
        byte_36 = byte_18 * byte_18
        byte_55 = byte_36 * byte_19
        byte_72 = byte_36 * byte_36
        byte_127 = byte_72 * byte_55
        byte_254 = byte_127 * byte_127
        return byte_254

    def invert_by_exponentiation_with_least_rounds(self, byte):
        byte_2 = byte * byte
        byte_3 = byte_2 * byte
        byte_4 = byte_2 * byte_2
        byte_7 = byte_4 * byte_3
        byte_8 = byte_4 * byte_4
        byte_15 = byte_8 * byte_7
        byte_16 = byte_8 * byte_8
        byte_31 = byte_16 * byte_15
        byte_32 = byte_16 * byte_16
        byte_63 = byte_32 * byte_31
        byte_64 = byte_32 * byte_32
        byte_127 = byte_64 * byte_63
        byte_254 = byte_127 * byte_127
        return byte_254

    # matrix for byte_sub, the last column is the translation vector
    A = Matrix([[1, 0, 0, 0, 1, 1, 1, 1],
                [1, 1, 0, 0, 0, 1, 1, 1],
                [1, 1, 1, 0, 0, 0, 1, 1],
                [1, 1, 1, 1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1, 0, 0, 0],
                [0, 1, 1, 1, 1, 1, 0, 0],
                [0, 0, 1, 1, 1, 1, 1, 0],
                [0, 0, 0, 1, 1, 1, 1, 1]])

    # anticipate bit recombination
    for i, row in enumerate(A.rows):
        for j in range(len(row)):
            row[j] *= 2 ** i

    def byte_sub(self, state, use_lin_comb=True):
        """ByteSub operation of Rijndael.

        The first argument should be a matrix consisting of elements
        of GF(2^8)."""

        for h in range(len(state)):
            row = state[h]

            for i in range(len(row)):
                bits = bit_decompose(self.invert(row[i]))

                if use_lin_comb:
                    row[i] = self.runtime.lin_comb(sum(AES.A.rows, []),
                                                   bits * len(AES.A.rows))
                else:
                    # caution: order is lsb first
                    vector = AES.A * Matrix(zip(bits))
                    bits = zip(*vector.rows)[0]
                    row[i] = sum(bits)

                row[i].addCallback(lambda x: 0x63 + x)

    def shift_row(self, state):
        """Rijndael ShiftRow.

        State should be a list of 4 rows."""

        assert len(state) == 4, "Wrong state size."

        if self.n_b in [4, 6]:
            offsets = [0, 1, 2, 3]
        else:
            offsets = [0, 1, 3, 4]

        for i, row in enumerate(state):
            for j in range(offsets[i]):
                row.append(row.pop(0))

    # matrix for mix_column
    C = [[2, 3, 1, 1],
         [1, 2, 3, 1],
         [1, 1, 2, 3],
         [3, 1, 1, 2]]

    C = Matrix(C)

    def mix_column(self, state, use_lin_comb=True):
        """Rijndael MixColumn.

        Input should be a list of 4 rows."""

        assert len(state) == 4, "Wrong state size."

        if use_lin_comb:
            columns = zip(*state)

            for i, row in enumerate(state):
                row[:] = [self.runtime.lin_comb(AES.C.rows[i], column)
                          for column in columns]
        else:
            state[:] = (AES.C * Matrix(state)).rows

    def add_round_key(self, state, round_key):
        """Rijndael AddRoundKey.

        State should be a list of 4 rows and round_key a list of
        4-byte columns (words)."""

        assert len(round_key) == self.n_b, "Wrong key size."
        assert len(round_key[0]) == 4, "Key must consist of 4-byte words."

        state[:] = (Matrix(state) + Matrix(zip(*round_key))).rows

    def key_expansion(self, key, new_length=None):
        """Rijndael key expansion.

        Input and output are lists of 4-byte columns (words).
        *new_length* is the round for which the key should be expanded.
        If ommitted, the key is expanded for all rounds."""

        assert len(key) >= self.n_k, "Wrong key size."
        assert len(key[0]) == 4, "Key must consist of 4-byte words."

        expanded_key = key

        if new_length == None:
            new_length = self.rounds

        for i in xrange(len(key), self.n_b * (new_length + 1)):
            temp = list(expanded_key[i - 1])

            if i % self.n_k == 0:
                temp.append(temp.pop(0))
                self.byte_sub([temp])
                temp[0] += GF256(2) ** (i / self.n_k - 1)
            elif self.n_k > 6 and i % self.n_k == 4:
                self.byte_sub([temp])

            new_word = []

            for j in xrange(4):
                new_word.append(expanded_key[i - self.n_k][j] + temp[j])

            expanded_key.append(new_word)

        return expanded_key

    def preprocess(self, input):
        if isinstance(input, str):
            return [Share(self.runtime, GF256, GF256(ord(c)))
                    for c in input]
        else:
            for byte in input:
                assert byte.field == GF256, \
                    "Input must be a list of GF256 elements " \
                    "or of shares thereof."
            return input

    def encrypt(self, cleartext, key, benchmark=False, prepare_at_once=False):
        """Rijndael encryption.

        Cleartext and key should be either a string or a list of bytes
        (possibly shared as elements of GF256)."""

        start = time.time()
        self.runtime.increment_pc()
        self.runtime.fork_pc()

        assert len(cleartext) == 4 * self.n_b, "Wrong length of cleartext."
        assert len(key) == 4 * self.n_k, "Wrong length of key."

        cleartext = self.preprocess(cleartext)
        key = self.preprocess(key)

        state = [cleartext[i::4] for i in xrange(4)]
        key = [key[4 * i:4 * i + 4] for i in xrange(self.n_k)]

        if benchmark:
            global preparation, communication
            preparation = 0
            communication = 0

            def progress(x, i, start_round):
                time_diff = time.time() - start_round
                global communication
                communication += time_diff
                print "Round %2d: %f, %f" % \
                      (i, time_diff, time.time() - start)
                return x

            def prep_progress(i, start_round):
                time_diff = time.time() - start_round
                global preparation
                preparation += time_diff
                print "Round %2d preparation: %f, %f" % \
                      (i, time_diff, time.time() - start)
        else:
            progress = lambda x, i, start_round: x
            prep_progress = lambda i, start_round: None

        expanded_key = self.key_expansion(key[:], 0)
        self.add_round_key(state, expanded_key[0:self.n_b])

        prep_progress(0, start)

        def get_trigger(state):
            return gather_shares(reduce(operator.add, state))

        def round(_, state, i):
            start_round = time.time()

            self.key_expansion(expanded_key, i)

            self.byte_sub(state)
            self.shift_row(state)
            self.mix_column(state)
            self.add_round_key(state, expanded_key[i * self.n_b:(i + 1) * self.n_b])

            if not prepare_at_once:
                trigger = get_trigger(state)
                trigger.addCallback(progress, i, time.time())

                if i < self.rounds - 1:
                    self.runtime.schedule_complex_callback(trigger, round, state, i + 1)
                else:
                    self.runtime.schedule_complex_callback(trigger, final_round, state)

            prep_progress(i, start_round)

            return _

        def final_round(_, state):
            start_round = time.time()

            self.key_expansion(expanded_key, self.rounds)

            self.byte_sub(state)
            self.shift_row(state)
            self.add_round_key(state, expanded_key[self.rounds * self.n_b:])

            trigger = get_trigger(state)
            trigger.addCallback(progress, self.rounds, time.time())

            if benchmark:
                trigger.addCallback(finish, state)

            # connect to final result
            for a, b in zip(reduce(operator.add, zip(*state)), result):
                a.addCallback(b.callback)

            prep_progress(self.rounds, start_round)

            return _

        def finish(_, state):
            print "Total preparation time: %f" % preparation
            print "Total communication time: %f" % communication

            return _

        result = [Share(self.runtime, GF256) for i in xrange(4 * self.n_b)]

        if prepare_at_once:
            for i in range(1, self.rounds):
                round(None, state, i)

            final_round(None, state)
        else:
            round(None, state, 1)

        self.runtime.unfork_pc()
        return result
