"""Allow `python -m src` as an alias; prefer `python -m src.cli`."""
from .cli import main

raise SystemExit(main())
