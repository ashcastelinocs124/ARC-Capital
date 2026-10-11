from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write via temp file + rename so readers never see a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _owner_alive(lock: Path) -> bool:
    try:
        pid = int(lock.read_text().strip())
        os.kill(pid, 0)
        return True
    except PermissionError:  # exists, owned by another user
        return True
    except (ValueError, OSError):  # no/garbage pid, or no such process
        return False


def acquire_lock(data_dir: Path, stale_seconds: int) -> bool:
    """Create data_dir/run.lock holding our PID; take over a dead or stale owner's lock."""
    lock = Path(data_dir) / "run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                fresh = time.time() - os.path.getmtime(lock) <= stale_seconds
                if fresh and _owner_alive(lock):
                    return False
                lock.unlink()  # owner died (killed server) or lock is stale
            except FileNotFoundError:
                continue
    return False


def release_lock(data_dir: Path) -> None:
    (Path(data_dir) / "run.lock").unlink(missing_ok=True)
