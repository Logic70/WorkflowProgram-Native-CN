#!/usr/bin/env python3
"""Compatibility wrapper for the renamed workflow maintenance guide generator."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    script = Path(__file__).resolve().with_name("generate-workflow-maintenance.py")
    args = sys.argv[1:]
    if not any(arg == "--out" or arg.startswith("--out=") for arg in args):
        args.extend(["--out", "workflow-lowlevel.md"])
    sys.argv = [str(script), *args]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
