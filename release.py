"""Build a clean zip of this project after the tests pass.   python release.py [tag]
Leaves out databases, logs, caches and virtual environments."""
import datetime as dt
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP_DIRS = {"__pycache__", "tle_cache", ".git", ".venv", "venv"}   # data/*.csv ARE shipped
SKIP_SUFFIX = {".db", ".db-wal", ".db-shm", ".log", ".pyc", ".zip"}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    if subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=HERE).returncode:
        sys.exit("Tests failed: release not built.")
    out = HERE.parent / f"{HERE.name}_{tag}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in HERE.rglob("*"):
            if p.is_file() and not (set(p.relative_to(HERE).parts) & SKIP_DIRS) and p.suffix not in SKIP_SUFFIX:
                z.write(p, Path(HERE.name) / p.relative_to(HERE))
    print("Built", out)


if __name__ == "__main__":
    main()
