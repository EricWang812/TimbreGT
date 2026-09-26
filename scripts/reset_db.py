"""Delete both SQLite databases (and their WAL sidecar files).

Usage: python -m scripts.reset_db   (normally via `make reset`, which re-seeds)

Written in Python rather than `rm -f` so `make reset` works from PowerShell
and cmd as well as Git Bash. Paths come from the same config the services use.
"""
from pathlib import Path

from api.config import MERCHANT_DB
from issuer.config import ISSUER_DB

SIDECAR_SUFFIXES = ("", "-wal", "-shm")


def main() -> None:
    for db in (MERCHANT_DB, ISSUER_DB):
        for suffix in SIDECAR_SUFFIXES:
            path = Path(f"{db}{suffix}")
            if path.exists():
                path.unlink()  # PermissionError here means a service still holds it: stop `make dev` first
                print(f"deleted {path}")


if __name__ == "__main__":
    main()
