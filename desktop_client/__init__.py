# Patch PyQt6 DLL directory path for Python 3.14 on Windows
import os
import sys

if sys.platform == "win32":
    try:
        import importlib.util
        spec = importlib.util.find_spec("PyQt6")
        if spec and spec.submodule_search_locations:
            pyqt6_dir = spec.submodule_search_locations[0]
            qt_bin_dir = os.path.join(pyqt6_dir, "Qt6", "bin")
            if os.path.isdir(qt_bin_dir):
                os.add_dll_directory(qt_bin_dir)
    except Exception:
        pass
