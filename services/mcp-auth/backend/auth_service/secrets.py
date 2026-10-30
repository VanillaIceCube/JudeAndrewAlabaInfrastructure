"""Read only bounded regular files belonging to the service UID."""
import os
import stat
from pathlib import Path


def protected_text(path, *, maximum, uid=65532):
    try:
        fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o400 or not 1 <= info.st_size <= maximum:
                raise ValueError()
            value = os.read(fd, maximum + 1).decode("utf-8")
            if not value.strip():
                raise ValueError()
            return value
        finally:
            os.close(fd)
    except (OSError, ValueError, UnicodeError):
        raise ValueError("Authorization service secret prerequisite failed") from None
