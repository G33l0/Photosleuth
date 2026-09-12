"""Background tasks.

Everything slow (EXIF parsing, geocoding, hashing, thumbnailing, network
requests) runs on a QThreadPool so the window never freezes.  Workers emit
signals and never touch widgets; each one is cancellable.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    """Signals shared by every worker (QRunnable cannot own signals itself)."""

    started = Signal()
    progress = Signal(int, int, str)      # done, total, current item
    result = Signal(object)               # one incremental result
    failed = Signal(str, str)             # item, error message
    finished = Signal(object)             # aggregate result
    cancelled = Signal()
    error = Signal(str)                   # fatal error


class CancelToken:
    """A plain flag the worker polls between items."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class BaseWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self.token = CancelToken()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.token.cancel()

    @Slot()
    def run(self) -> None:  # pragma: no cover - exercised through the pool
        try:
            self.signals.started.emit()
            self.work()
        except Exception:
            self.signals.error.emit(traceback.format_exc(limit=6))

    def work(self) -> None:
        raise NotImplementedError


class AnalyzeWorker(BaseWorker):
    """Extract metadata (and optionally forensics) for a list of images."""

    def __init__(
        self,
        paths: Iterable,
        geocode: bool = True,
        forensics: bool = False,
        custody: bool = True,
    ) -> None:
        super().__init__()
        self.paths: List[Path] = [Path(p) for p in paths]
        self.geocode = geocode
        self.forensics = forensics
        self.custody = custody

    def work(self) -> None:
        from ..core import extract_metadata

        results: List[Dict[str, Any]] = []
        total = len(self.paths)

        for index, path in enumerate(self.paths, start=1):
            if self.token.cancelled:
                self.signals.cancelled.emit()
                self.signals.finished.emit(results)
                return

            self.signals.progress.emit(index - 1, total, path.name)
            try:
                metadata = extract_metadata(path, geocode=self.geocode)
            except Exception as exc:  # noqa: BLE001 - report and keep going
                self.signals.failed.emit(str(path), str(exc))
                continue

            if self.forensics:
                try:
                    from .. import forensics as forensics_module

                    metadata["forensics"] = forensics_module.analyze(path, metadata)
                except Exception as exc:  # noqa: BLE001
                    metadata["forensics_error"] = str(exc)

            if self.custody:
                try:
                    from .. import custody as custody_module

                    custody_module.record("analyze", path, {"geocode": self.geocode})
                except Exception:
                    pass

            results.append(metadata)
            self.signals.result.emit(metadata)

        self.signals.progress.emit(total, total, "")
        self.signals.finished.emit(results)


class ThumbnailWorker(BaseWorker):
    """Decode thumbnails off the UI thread.

    QPixmap may only be touched on the GUI thread, so this emits QImages and
    the view converts them.
    """

    def __init__(self, paths: Iterable, size: int = 160) -> None:
        super().__init__()
        self.paths: List[Path] = [Path(p) for p in paths]
        self.size = int(size)

    def work(self) -> None:
        from PIL import Image, ImageOps

        from .resources import pil_to_qimage

        total = len(self.paths)
        for index, path in enumerate(self.paths, start=1):
            if self.token.cancelled:
                self.signals.cancelled.emit()
                self.signals.finished.emit(None)
                return
            try:
                with Image.open(path) as image:
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((self.size, self.size), Image.LANCZOS)
                    qimage = pil_to_qimage(image.convert("RGB"))
                self.signals.result.emit((str(path), qimage))
            except Exception as exc:  # noqa: BLE001
                self.signals.failed.emit(str(path), str(exc))
            self.signals.progress.emit(index, total, path.name)
        self.signals.finished.emit(None)


class ForensicsWorker(BaseWorker):
    """Run the forensic checks over a set of already-analysed images."""

    def __init__(self, records: List[Dict[str, Any]]) -> None:
        super().__init__()
        self.records = list(records)

    def work(self) -> None:
        from .. import forensics as forensics_module

        output: Dict[str, Dict[str, Any]] = {}
        total = len(self.records)
        for index, metadata in enumerate(self.records, start=1):
            if self.token.cancelled:
                self.signals.cancelled.emit()
                self.signals.finished.emit(output)
                return
            path = metadata.get("file", "")
            self.signals.progress.emit(index - 1, total, Path(path).name if path else "")
            try:
                report = forensics_module.analyze(path, metadata)
                output[path] = report
                self.signals.result.emit(report)
            except Exception as exc:  # noqa: BLE001
                self.signals.failed.emit(path, str(exc))
        self.signals.progress.emit(total, total, "")
        self.signals.finished.emit(output)


class SearchWorker(BaseWorker):
    """Reverse image search for one file."""

    def __init__(self, path, engine: str) -> None:
        super().__init__()
        self.path = Path(path)
        self.engine = engine

    def work(self) -> None:
        from ..search import SearchError, reverse_image_search

        try:
            result = reverse_image_search(self.path, engine=self.engine)
        except (SearchError, OSError) as exc:
            self.signals.failed.emit(str(self.path), str(exc))
            self.signals.finished.emit(None)
            return

        try:
            from .. import custody as custody_module

            custody_module.record("reverse_search", self.path, {"engine": self.engine})
        except Exception:
            pass

        self.signals.result.emit(result)
        self.signals.finished.emit(result)


class CallableWorker(BaseWorker):
    """Run any callable in the pool and hand back its return value."""

    def __init__(self, function: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def work(self) -> None:
        try:
            value = self.function(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(getattr(self.function, "__name__", "task"), str(exc))
            self.signals.finished.emit(None)
            return
        self.signals.result.emit(value)
        self.signals.finished.emit(value)


class TaskRunner(QObject):
    """Owns the thread pool and the currently running workers."""

    busyChanged = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None, max_threads: int = 0) -> None:
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        if max_threads > 0:
            self.pool.setMaxThreadCount(max_threads)
        self._active: List[BaseWorker] = []

    def start(self, worker: BaseWorker) -> BaseWorker:
        self._active.append(worker)
        worker.signals.finished.connect(lambda _=None, w=worker: self._retire(w))
        worker.signals.error.connect(lambda _msg, w=worker: self._retire(w))
        if len(self._active) == 1:
            self.busyChanged.emit(True)
        self.pool.start(worker)
        return worker

    def _retire(self, worker: BaseWorker) -> None:
        if worker in self._active:
            self._active.remove(worker)
        if not self._active:
            self.busyChanged.emit(False)

    @property
    def busy(self) -> bool:
        return bool(self._active)

    def cancel_all(self) -> None:
        for worker in list(self._active):
            worker.cancel()

    def wait(self, timeout_ms: int = 30000) -> bool:
        return self.pool.waitForDone(timeout_ms)
