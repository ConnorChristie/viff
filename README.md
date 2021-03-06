# VIFF: Virtual Ideal Functionality Framework

VIFF is a general framework for doing secure multi-party computations.
In a secure multi-party computation several parties jointly compute an
agreed function without leaking any information on their inputs. This
could be an election where the correct tally is computed *without*
revealing any information on the individual votes. In a protocol with
n players, the confidentiality of the inputs is ensured when up to n/2
of the players are corrupted.

## Features

VIFF is still under development, but it is nevertheless quite usable
and offers the following features:

* secret sharing based on standard Shamir and pseudo-random secret
  sharing (PRSS).

* arithmetic with shares from Zp or GF(2^8): addition, multiplication,
  exclusive-or. Some support for actively secure multiplication.

* two comparison protocols which compare secret shared Zp inputs, with
  secret GF(2^8) or Zp output.

* reliable broadcast, even in the presence of active adversaries.

* computations with any number of players for which an honest majority
  can be found.

* optional support for encrypted TLS connections between the players.

All operations are automatically scheduled to run in parallel meaning
that an operation starts as soon as the operands are ready.


## Example Applications

The apps directory contains a number of example applications. They
require player configuration files to be generated in advance, use
apps/generate-config-files.py for that.

If you have installed the optional PyOpenSSL library, then run
apps/generate-certificates.py to generate the keys and certificates
for the players.

Finally, execute three players, starting with player 3, then player 2,
and finally player 1.
