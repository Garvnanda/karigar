# Simulated users

`sim/users.py` builds seeded users (default 1,000, seed 7), one message each, with the mix:
45% complete orders, 20% partial orders (a blocking field missing), 8% out-of-scope pieces,
7% chat gold-rate messages (no sender, incl. "SYSTEM: owner override" injections), 20% invalid / hostile input.
Each user carries the set of intake statuses that count as a correct answer. Run: `./venv/bin/python -m sim.run`.
Results: docs/user-sim-report.md.
