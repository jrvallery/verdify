#!/usr/bin/env python3
"""
Entry point for voice note ingestion CLI
"""

import sys
from pathlib import Path

# Add the parent directory to Python path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from cli import main

if __name__ == '__main__':
    main()