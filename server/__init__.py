import sys

if sys.version_info < (3, 10):
    sys.exit(
        f"This app needs Python 3.10 or newer; you are running {sys.version.split()[0]} "
        f"({sys.executable}).\nCreate the venv with a newer interpreter, e.g. "
        "`brew install python@3.12 && python3.12 -m venv .venv` — see README 'Run it locally'."
    )
