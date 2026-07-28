"""Real Bilibili live-room verification tests.

These tests exercise the recorder against the live Bilibili service instead of
the fake server used by the system tests. They are network-dependent and
opt-in: nothing here runs unless ``BIREC_REALBILI=1`` is set in the
environment. The quality gate and CI (``-m "unit or component"``) never select
them, and the standalone scheduled workflow drives them separately.
"""
