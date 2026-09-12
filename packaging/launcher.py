#!/usr/bin/env python3
"""Frozen-application entry point.

Running ``PhotoSleuth.exe`` with no arguments (or with image paths, which is how
Explorer's "Open with" and the file associations call it) opens the desktop
app.  ``photosleuth-cli.exe`` and the ``--cli`` switch reach the command line.
"""

from __future__ import annotations

import multiprocessing
import os
import sys


def main() -> int:
    # Required or a frozen app can re-launch itself when a child process starts.
    multiprocessing.freeze_support()

    arguments = sys.argv[1:]
    executable = os.path.basename(sys.argv[0]).lower()

    wants_cli = "--cli" in arguments or "cli" in executable
    if wants_cli:
        arguments = [item for item in arguments if item != "--cli"]
        from photosleuth.cli import main as cli_main

        return cli_main(arguments)

    from photosleuth.gui.app import run

    return run(arguments)


if __name__ == "__main__":
    sys.exit(main())
