#!/usr/bin/env python

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

# This file contains a simpel example of a VIFF program, which illustrates
# the basic features of VIFF. How to input values from the command line,
# from individual players in the program, add, multiply, and output values
# to all or some of the players.

# Inorder to run the program follow the three steps:
#
# Generate player configurations in the viff/apps directory using:
#   python generate-config-files.py localhost:4001 localhost:4002 localhost:4003
#
# Generate ssl certificates in the viff/apps directory using:
#   python generate-certificates.py
#
# Run the program using three different shells using the command:
#   python beginner.py player-x.ini 79
# where x is replaced by the player number

import random
import sys
# Some useful imports.
from time import time

import viff.reactor

viff.reactor.install()
from twisted.internet import reactor

from viff.math.field import GF
from viff.runtime import create_runtime, make_runtime_class
from viff.config import load_config
from viff.utils.util import dprint, find_prime
from viff.mixins.equality import ProbabilisticEqualityMixin
from viff.mixins.comparison import Toft05Runtime

# Load the configuration from the player configuration files.
id, players = load_config(sys.argv[1])

# Initialize the field we do arithmetic over.
field_length = 256
Zp = GF(find_prime(2 ** field_length, blum=True))


def get_accounts(length, runtime):
    accounts = []

    for x in range(length):
        if x == 9:
            accounts.append(runtime.input([1], Zp, 0x3134f954AFf7F5F8EB849a80Fb85447E5b2a3696))
        else:
            accounts.append(runtime.input([1], Zp, random.randint(0, Zp.field.modulus)))
        accounts.append(runtime.input([1], Zp, random.randint(0, 6000)))
        accounts.append(runtime.input([1], Zp, random.randint(0, 6000)))

    return accounts


def protocol(runtime):
    print "Program started"
    start_time = time()

    num_accounts = 50

    if runtime.id == 1:
        from_id = runtime.input([1], Zp, 9)
        # other_id = runtime.input([1], Zp, 999)
        # gf_256 = runtime.input([1], GF256, 21)
        from_pubkey = runtime.input([1], Zp, 0x3134f954AFf7F5F8EB849a80Fb85447E5b2a3696)

        arr = get_accounts(num_accounts, runtime)
    else:
        from_id = runtime.input([1], Zp, None)
        # other_id = runtime.input([1], Zp, None)
        # gf_256 = runtime.input([1], GF256, None)
        from_pubkey = runtime.input([1], Zp, None)

        arr = [runtime.input([1], Zp, None) for x in range(num_accounts * 3)]

    owner_pubkey = 0
    value = 0

    for i in range(num_accounts):
        if runtime.id == 1:
            id_share = runtime.shamir_share([1], Zp, i)
        else:
            id_share = runtime.shamir_share([1], Zp, None)

        equality = runtime.equal(from_id, id_share)

        dprint("%s == %s: %s", runtime.open(from_id), runtime.open(id_share), runtime.open(equality))

        owner_pubkey += arr[i * 3] * equality
        value += arr[i * 3 + 2] * equality

    output = (from_pubkey == owner_pubkey) * value
    output = runtime.open(output)

    dprint("output %s", output)

    actual = runtime.open(arr[9 * 3 + 2])
    dprint("actual %s", actual)

    print "Time taken: %.2f sec" % (time() - start_time)

    runtime.wait_for(output)

    # runtime.schedule_callback(results, lambda _: runtime.synchronize())
    # runtime.schedule_callback(results, lambda _: runtime.shutdown())


def errorHandler(failure):
    print "Error: %s" % failure


# Create a runtime
runtime_class = make_runtime_class(runtime_class=Toft05Runtime, mixins=[ProbabilisticEqualityMixin])
pre_runtime = create_runtime(id, players, 1, None, runtime_class)
pre_runtime.addCallback(protocol)
# This error handler will enable debugging by capturing
# any exceptions and print them on Standard Out.
pre_runtime.addErrback(errorHandler)

print "#### Starting reactor ###"
reactor.run()
