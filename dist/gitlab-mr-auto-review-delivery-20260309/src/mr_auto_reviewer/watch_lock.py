import os
from pathlib import Path
from typing import Optional


class WatchProcessLock:
    def __init__(self, lock_path: Path, pid: Optional[int] = None):
        self.lock_path = Path(lock_path)
        self.pid = int(pid or os.getpid())
        self._acquired = False

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(f"{self.pid}\n")
                self._acquired = True
                return True
            except FileExistsError:
                existing_pid = self._read_pid()
                if existing_pid is not None and self._is_pid_running(existing_pid):
                    return False
                self._unlink_if_exists()

    def release(self) -> None:
        if not self._acquired:
            return
        current_pid = self._read_pid()
        if current_pid == self.pid:
            self._unlink_if_exists()
        self._acquired = False

    def _read_pid(self) -> Optional[int]:
        try:
            raw = self.lock_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @staticmethod
    def _is_pid_running(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

    def _unlink_if_exists(self) -> None:
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return
