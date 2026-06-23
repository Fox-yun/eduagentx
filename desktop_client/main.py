import sys
import os
# Patch PyQt6 DLL directory path for Python 3.14 on Windows
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

from PyQt6.QtWidgets import QApplication

from desktop_client.widgets.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    # Load stylesheet
    style_path = os.path.join(os.path.dirname(__file__), "styles", "app.qss")
    try:
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"Warning: Stylesheet not found at {style_path}")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
