"""Convenient Windows entry point; equivalent to ``python -m orbit``."""

from orbit.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
