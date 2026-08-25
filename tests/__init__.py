"""The meterline test suite.

Run it with the standard library runner:

    python -m unittest discover -s tests -t .

There are no third-party test dependencies, for the same reason the engine
has no runtime ones: a determinism claim is easier to defend when nothing
underneath it can change between two runs.
"""
