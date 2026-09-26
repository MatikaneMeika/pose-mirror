"""pose-mirror launcher.

Entry point for the PyInstaller bundle (``pose-mirror.exe``) and a
convenient dev shortcut: ``python main.py`` from the project root.

When frozen, ``posemirror`` is already inside the bundle, so the
``sys.path`` tweak below is a harmless no-op.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from posemirror.server import main  # noqa: E402

if __name__ == "__main__":
    main()
