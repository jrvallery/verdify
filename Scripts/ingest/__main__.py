#!/usr/bin/env python3
"""
CLI entry point for voice note ingestion pipeline.
"""

import sys
import os

# Add the Scripts directory to the Python path so we can import the ingest module
script_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.dirname(script_dir)
sys.path.insert(0, scripts_dir)

from ingest.cli import main

if __name__ == "__main__":
    main()