#!/usr/bin/env python3
"""
Brother P-touch Cube PT-P300BT Label Studio
Entrypoint script.
"""

import sys
import os

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.app import main

if __name__ == "__main__":
    main()
