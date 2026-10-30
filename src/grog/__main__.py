"""Allow ``python -m grog`` as an equivalent of the ``grog`` entry point."""

from grog.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
