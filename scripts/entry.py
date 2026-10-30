"""Entry point used by PyInstaller builds."""

import sys

from bilicli.cli import main

if __name__ == "__main__":
    sys.exit(main())
