"""Test package bootstrap: make sibling helper modules (lint_test_utils)
importable regardless of how unittest is invoked."""
import sys
from pathlib import Path

_here = str(Path(__file__).parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
