"""Allow `python -m ahut_electricity`."""

import sys

from .cli import main

sys.exit(main())
