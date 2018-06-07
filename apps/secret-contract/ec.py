#!/usr/bin/env python

# Copyright 2008 VIFF Development Team.
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

# This is an implementation of the example program (Figure 6) used by
# Janus Dam Nielsen and Michael I. Schwartzbach in their paper "A
# Domain-Specific Programming Language for Secure Multiparty
# Computation" presented at the PLAS '07 conference. The program
# evaluates a polynomial securely and reveals the sign of the result.

from optparse import OptionParser
from time import time

import viff.reactor

viff.reactor.install()
from twisted.internet import reactor

from viff.math.field import GF
from viff.runtime import Runtime, create_runtime
from viff.config import load_config


def divide(x, y, l):
    """Returns a share of of ``x/y`` (rounded down).

       Precondition:  ``2**l * y < x.field.modulus``.

       If ``y == 0`` return ``(2**(l+1) - 1)``.

       The division is done by making a comparison for every
       i with ``(2**i)*y`` and *x*.
       Protocol by Sigurd Meldgaard.

       Communication cost: *l* rounds of comparison.

       Also works for simple integers:
       >>>divide(3, 3, 2)
       1
       >>>divide(50, 10, 10)
       5
       """
    bits = []
    for i in range(l, -1, -1):
        t = 2 ** i * y
        cmp = t <= x
        bits.append(cmp)
        x = x - t * cmp
    return bits_to_val(bits)


# We start by defining the protocol.
def eval_poly(runtime):
    print "Starting protocol"
    start_time = time()

    Zp = GF(57896044618658097711785492504343953926634992332820282019728792003956564819949)

    # Gx = 0x2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad245a
    # Gy = 0x20ae19a1b8a086b4e01edd2c7748d14c923d4d7e6d7c61b229e9c5a27eced3d9

    # In this example we just let Player 1 share the input values.
    if runtime.id == 1:
        x = runtime.shamir_share([1], Zp, 0x656773b68b20e9d9b4332081b21898bae504c1088a8b28595c4704a301b8f722)  # x1
        a = runtime.shamir_share([1], Zp, 0x13b5d4c07675266c9d07f91b07d48ef0fdbe9b4e24e2992304901ac2a97b59f1)  # y1
        b = runtime.shamir_share([1], Zp, 0x5a1e4aff484be0404f28de08a82f7b32271260b5c803963991c3fa7376c2de77)  # x2
        c = runtime.shamir_share([1], Zp, 0x41f6d23c8f62c91f9ec4f6d64dd0994c9c2441c1ed65cc4e1c97e9d68a9de169)  # y2
    else:
        x = runtime.shamir_share([1], Zp)
        a = runtime.shamir_share([1], Zp)
        b = runtime.shamir_share([1], Zp)
        c = runtime.shamir_share([1], Zp)

    # x: 7ff0a38a625bbb21d7da773abf0f2af4bcebc4846898943bde295589d0c29e09
    # y: 5b7ac2e700968c81b0af36b611061653b4d916082cac0012295ddcf9c1954641

    # Evaluate the polynomial.
    # p = a * (x * x) + b * x + c

    lam = divide(c - a, b - x, 64)
    # x3 = (lam * lam) - x - b
    # y3 = lam * (x - x3) - a

    output1 = runtime.open(lam)
    # output2 = runtime.open(y3)
    output1.addCallback(done, start_time, runtime)
    # output2.addCallback(done, start_time, runtime)

    runtime.wait_for(output1)


def done(sign, start_time, runtime):
    print "Sign: %s" % sign
    print "Time taken: %.2f sec" % (time() - start_time)


# Parse command line arguments.
parser = OptionParser()
Runtime.add_options(parser)
options, args = parser.parse_args()

if len(args) == 0:
    parser.error("you must specify a config file")
else:
    id, players = load_config(args[0])

# Create a deferred Runtime and ask it to run our protocol when ready.
pre_runtime = create_runtime(id, players, 1)
pre_runtime.addCallback(eval_poly)

# Start the Twisted event loop.
reactor.run()
