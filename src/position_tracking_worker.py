"""One running job, no waiting queue, no claim that timeout cancels filesystem I/O."""
from concurrent.futures import Future
import threading


class SingleFlightWorker:
    def __init__(self, name):
        self.name = name
        self._lock = threading.Lock()
        self._future = None
        self._closed = False

    def submit(self, function, *args):
        with self._lock:
            if self._closed or (self._future is not None and not self._future.done()):
                raise RuntimeError("Υπάρχει ήδη εργασία σε εξέλιξη.")
            future = Future()
            future.set_running_or_notify_cancel()
            self._future = future

            def run():
                try:
                    value = function(*args)
                except BaseException as error:
                    future.set_exception(error)
                else:
                    future.set_result(value)

            threading.Thread(target=run, name=self.name, daemon=True).start()
            return future

    def close(self):
        with self._lock:
            # This only rejects NEW jobs. Running work remains owned until it
            # completes or the process exits; durable central recovery handles
            # a process dying after an event commit.
            self._closed = True
