#!/usr/bin/env python3
"""
Video Speeder CLI - Fast Local Video Speed Multiplier Engine.
"""

import sys

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from video_speeder.cli import main

if __name__ == "__main__":
    sys.exit(main())
