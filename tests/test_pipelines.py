"""Smoke: the demo quiz renders and passes every gate (about 1-2 minutes)."""
import subprocess
import sys


def test_demo_passes_qa():
    r = subprocess.run([sys.executable, "-m", "va.cli", "demo"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
