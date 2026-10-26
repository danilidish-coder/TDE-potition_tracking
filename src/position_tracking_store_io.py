"""Shared file locking, atomic receipts and SQLite connection primitives."""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
import json
import os
import sqlite3
import time
import uuid
from position_tracking_common import _safe_name

class BusyError(RuntimeError):
    pass


class StoreIOMixin:
    def _active_path(self, agms: str) -> Path:
        return self.active / f"{_safe_name(agms)}.json"


    def _lock_path(self, agms: str) -> Path:
        return self.locks / f"{_safe_name(agms)}.lock"


    @staticmethod
    @contextmanager
    def _file_lock(path: Path, timeout: float, busy_message: str):
        """OS-held byte-range lock. The lock file stays in place on SMB.

        Unlike stale-file mtime locks, Windows releases this lock when the
        owning process dies or its SMB handle is disconnected. Never unlink
        another process's lock based on its age.
        """
        import errno
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
        except OSError as exc:
            raise BusyError(f"Δεν είναι διαθέσιμος ο κοινόχρηστος φάκελος: {exc}") from exc
        locked = False
        try:
            # Never write a bootstrap byte BEFORE acquiring the OS lock.
            # On Windows/SMB a concurrent owner may already lock byte 0;
            # os.write(fd, b"\x00") then fails with EACCES and was treated as
            # a fatal error rather than normal lock contention. Both Windows
            # byte-range locks and POSIX flock support empty lock files.
            deadline = time.monotonic() + timeout
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except OSError as exc:
                    contention = exc.errno in (errno.EACCES, errno.EAGAIN) or getattr(exc, "winerror", None) in (32, 33, 36)
                    if not contention:
                        raise BusyError(f"Αποτυχία κοινόχρηστου κλειδώματος: {exc}") from exc
                    if time.monotonic() >= deadline:
                        raise BusyError(busy_message) from exc
                    time.sleep(0.15)
            yield
        finally:
            if locked:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
            else:
                os.close(fd)


    @contextmanager
    def officer_lock(self, agms: str, timeout: float = 6.0):
        with self._file_lock(
            self._lock_path(agms), timeout,
            "Η καταχώριση χρησιμοποιείται από άλλο σταθμό. Δοκιμάστε ξανά."
        ):
            yield


    @staticmethod
    def _atomic_json(path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)


    @contextmanager
    def _shift_db_write_lock(self, timeout: float = 10.0):
        with self._file_lock(
            self.locks / "shift_reports.sqlite.lock", timeout,
            "Το αρχείο βαρδιών χρησιμοποιείται από άλλο σταθμό. Δοκιμάστε ξανά."
        ):
            yield


    @contextmanager
    def _shift_db_connect(self):
        con = sqlite3.connect(str(self.shift_db), timeout=10.0)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=DELETE")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA busy_timeout=10000")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

