#!/usr/bin/env python3
"""Entry point for ss-transcriber.

- No arguments  →  launches the desktop GUI.
- With arguments  →  runs the CLI (see `ss-transcriber --help`).
"""
import multiprocessing
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "--gui":
        from ss_transcriber.cli import main as cli_main
        cli_main()
    else:
        from ss_transcriber.gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
