"""Isolated Windows trial entry: lean operator by default, officer via argument.

Never use this wrapper to overwrite an approved production build.
"""
import sys
from position_tracking import run

if __name__ == "__main__":
    args = list(sys.argv)
    if "--central-officer" not in args and "--central-only" not in args:
        args.append("--central-only")
    raise SystemExit(run(args))
