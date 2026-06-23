from PyQt6.QtCore import QThread, pyqtSignal

class ApiCallWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, callback, *args, **kwargs):
        super().__init__()
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.callback(*self.args, **self.kwargs)
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
