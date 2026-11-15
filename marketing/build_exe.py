"""Build the StockOffline Windows executable.

Kept local only (not committed to the published repo).

Usage:
    python marketing/build_exe.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "StockOffline.spec")


if __name__ == "__main__":
    cmd = [
        sys.executable, "-m", "PyInstaller",
        SPEC,
        "--distpath", os.path.join("marketing", "dist"),
        "--workpath", os.path.join("marketing", "build"),
        "--noconfirm",
        "--clean",
    ]
    sys.exit(subprocess.call(cmd, cwd=ROOT))
