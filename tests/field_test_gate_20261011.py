"""Regression gate trigger for Windows test run, 2026-10-11.

The existing Windows workflow executes:
- repeated old AGMS handoff / rejected offline END regression;
- 15-client restart stress;
- intermittent SMB connection and local queue recovery;
- GUI stall and central shared EXE regression;
- historical shift/report regression.

This file is intentionally non-invasive. No production runtime changes.
"""
def test_marker():
    assert True
