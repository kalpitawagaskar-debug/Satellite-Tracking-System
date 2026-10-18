"""Run:  python check_env.py     Tells you which Python VS Code uses and what is missing."""
import importlib
import sys

print("Python :", sys.version.split()[0])
print("Path   :", sys.executable)
missing = []
for mod, need in (("tkinter", "always"), ("sqlite3", "always"), ("pandas", "always"), ("numpy", "always"),
                  ("skyfield", "real satellites"), ("sgp4", "real satellites / archived orbits")):
    try:
        m = importlib.import_module(mod)
        print(f"  OK      {mod:9s} {getattr(m, '__version__', '')}")
    except ImportError:
        print(f"  MISSING {mod:9s} needed for: {need}")
        missing.append(mod)
if missing:
    py = f'"{sys.executable}"'
    if "tkinter" in missing:
        print("\\nTkinter is missing: reinstall Python from python.org and tick 'tcl/tk and IDLE'.")
    print(f"\nFix (installs into THIS Python):\n  {py} -m pip install -r requirements.txt")
else:
    print("\nEverything needed is installed. Run:  python app.py --demo")
