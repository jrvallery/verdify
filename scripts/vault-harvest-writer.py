#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Compatibility wrapper for harvest operation vault output."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("vault-operations-writer.py")), run_name="__main__")
