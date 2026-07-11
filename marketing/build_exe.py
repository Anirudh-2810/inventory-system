"""Build a standalone StockOffline GUI executable.

The shop computer does NOT need Python installed — this produces a single
double-click .exe file.

Requirements (run once on YOUR machine):
    pip install pyinstaller

Usage (from the project root):
    python marketing/build_exe.py

Output:
    marketing/dist/StockOffline.exe   <-- copy this to the shop PC
    (inventory.db is created next to the exe on first run)

Notes:
    - Build on the same OS you'll deploy to (Windows .exe on Windows).
    - The .exe bundles the offline GUI (gui.py) and the inventory_system package.
    - After building, test by running dist/StockOffline.exe once yourself.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_GUI = os.path.abspath(os.path.join(HERE, "..", "src", "gui.py"))


def main() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found. Install it with: pip install pyinstaller")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "StockOffline",
        "--distpath", os.path.join(HERE, "dist"),
        "--workpath", os.path.join(HERE, "build"),
        "--clean",
        SRC_GUI,
    ]
    print("Building:\n  " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed (exit {e.returncode}).")
        print("Common fix: ensure 'pip install pyinstaller' succeeded and")
        print("that src/gui.py runs normally with 'python src/gui.py'.")
        sys.exit(e.returncode)

    exe = os.path.join(HERE, "dist", "StockOffline.exe")
    if os.path.exists(exe):
        print(f"\nDONE. Copy this single file to the shop PC:\n  {exe}")
        print("The shop owner double-clicks it — no Python needed.")
    else:
        print("\nBuild finished but exe not found — check the output above.")


if __name__ == "__main__":
    main()
