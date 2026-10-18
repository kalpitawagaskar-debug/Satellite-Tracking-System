"""Keep Tkinter responsive: run slow work (CSV import, network, pandas) off the UI thread and
hand results back on the UI thread. Tk widgets must only be touched from the main thread.
"""
import logging
import queue
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)


class UserFacingError(Exception):
    """Expected problems (missing package, no internet, bad CSV). Shown to the user as one line,
    without a stack trace in the console."""


class TkWorker:
    """submit(fn, *a, on_done=cb, on_error=cb). Callbacks run on the Tk main thread.
    root only needs .after(ms, fn) and .after_cancel(id) (tk.Tk() works).

    The worker also keeps a strong reference to every job's function and callbacks on the MAIN thread
    until the result has been delivered. Otherwise a worker thread could drop the last reference to a
    Tk object (the window) and Python would free it from the wrong thread, which aborts Tcl/Tk."""

    def __init__(self, root, workers=2, poll_ms=40):
        self.root, self.poll_ms = root, poll_ms
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tkworker")
        self._q, self._alive, self._keep = queue.Queue(), True, {}
        self._after_id = self.root.after(poll_ms, self._poll)

    def submit(self, fn, *args, on_done=None, on_error=None, **kw):
        token = object()
        self._keep[token] = (fn, args, kw, on_done, on_error)          # main thread owns these references

        def job():
            try:
                res = fn(*args, **kw)
                self._q.put((token, on_done, res))
            except UserFacingError as exc:
                log.warning("%s: %s", getattr(fn, "__name__", fn), exc)
                self._q.put((token, on_error, exc))
            except Exception as exc:  # noqa: BLE001 - report every failure to the UI thread
                log.exception("worker job failed: %s", getattr(fn, "__name__", fn))
                self._q.put((token, on_error, exc))
        self._pool.submit(job)

    def call_soon(self, fn, *args):
        """Thread-safe: run fn(*args) on the main thread."""
        self._q.put((None, lambda _r: fn(*args), None))

    def pump(self):
        while True:
            try:
                token, cb, payload = self._q.get_nowait()
            except queue.Empty:
                return
            if cb:
                try:
                    cb(payload)
                except Exception:  # noqa: BLE001
                    log.exception("UI callback failed")
            self._keep.pop(token, None)

    def _poll(self):
        if not self._alive:
            return
        self.pump()
        self._after_id = self.root.after(self.poll_ms, self._poll)

    def shutdown(self):
        self._alive = False
        try:
            self.root.after_cancel(self._after_id)
        except Exception:  # noqa: BLE001
            pass
        self._pool.shutdown(wait=False, cancel_futures=True)


class Debouncer:
    """Call fn once, ms after the last trigger (use for resize / search-box redraws)."""

    def __init__(self, root, ms, fn):
        self.root, self.ms, self.fn, self._id = root, ms, fn, None

    def __call__(self, *_):
        if self._id is not None:
            self.root.after_cancel(self._id)
        self._id = self.root.after(self.ms, self._fire)

    def _fire(self):
        self._id = None
        self.fn()
