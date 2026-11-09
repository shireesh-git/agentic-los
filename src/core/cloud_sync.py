"""Keep the demo's data across Cloud Run restarts and redeploys (critical fix #2).

Cloud Run's disk is wiped whenever the instance stops (about 15 minutes idle) or a new revision is deployed.
With ``CAM_STATE_BUCKET`` set, this module

    restore()  at startup, before the database is opened: copies the latest saved database and uploaded files
               down from the bucket (the image's demo snapshot is used only when the bucket is empty)
    start()    every ``interval`` seconds, and once more on shutdown: copies the database (a consistent SQLite
               backup, never the live file) and any new or changed uploaded file up to the bucket

The service runs one instance at a time (max-instances 1), so there is a single writer. At most one interval
of work can be lost if the instance is killed without warning. Without ``CAM_STATE_BUCKET`` (a laptop) nothing
here runs.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Optional

from src.core.runtime_paths import DOCUMENTS_ROOT, RUNTIME_DB_PATH, STORAGE_ROOT

log = logging.getLogger(__name__)

PREFIX = "state/"
DB_OBJECT = PREFIX + "cam_platform.sqlite3"


def _bucket():
    name = os.getenv("CAM_STATE_BUCKET", "").strip()
    if not name:
        return None
    from google.cloud import storage
    return storage.Client().bucket(name)


def _synced_dirs() -> list[tuple[Path, str]]:
    """Folders that hold files people upload: proposal documents, and new prospects' documents (P… ids)."""
    dirs = [(STORAGE_ROOT / "flow", PREFIX + "flow/"),
            # what reading each document produced: a restart does not read the same documents again
            (STORAGE_ROOT / "cache" / "extractions", PREFIX + "cache/extractions/")]
    if DOCUMENTS_ROOT.exists():
        dirs += [(d, PREFIX + f"documents/{d.name}/") for d in DOCUMENTS_ROOT.iterdir()
                 if d.is_dir() and d.name.startswith("P")]
    return dirs


def restore() -> bool:
    """Bring the saved state down; True when a saved database was restored."""
    bucket = _bucket()
    if bucket is None:
        return False
    restored = False
    try:
        blob = bucket.blob(DB_OBJECT)
        if blob.exists():
            RUNTIME_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            for suffix in ("-wal", "-shm"):                      # never mix a saved db with the image's journal
                Path(str(RUNTIME_DB_PATH) + suffix).unlink(missing_ok=True)
            blob.download_to_filename(str(RUNTIME_DB_PATH))
            restored = True
        for blob in bucket.list_blobs(prefix=PREFIX):
            rel = blob.name[len(PREFIX):]
            if not rel or rel.endswith("/") or blob.name == DB_OBJECT:
                continue
            target = (STORAGE_ROOT / rel) if not rel.startswith("documents/") else (DOCUMENTS_ROOT / rel[10:])
            target.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(target))
        log.info("Cloud state restored from gs://%s (%s)", bucket.name,
                 "saved database" if restored else "no saved database yet: using the image's demo data")
    except Exception:
        log.exception("Cloud state restore failed — starting from the image's demo data")
    return restored


class Syncer:
    def __init__(self, bucket, interval: float = 60.0):
        self.bucket = bucket
        self.interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._db_stamp: Optional[tuple] = None
        self._files: dict[str, float] = {}

    def _db_changed(self) -> bool:
        stamp = tuple((p.stat().st_mtime, p.stat().st_size) if p.exists() else None
                      for p in (RUNTIME_DB_PATH, Path(str(RUNTIME_DB_PATH) + "-wal")))
        changed = stamp != self._db_stamp
        self._db_stamp = stamp
        return changed

    def sync(self) -> None:
        with self._lock:
            try:
                if RUNTIME_DB_PATH.exists() and self._db_changed():
                    with tempfile.TemporaryDirectory() as tmp:
                        copy = Path(tmp) / "snapshot.sqlite3"
                        src, dst = sqlite3.connect(RUNTIME_DB_PATH), sqlite3.connect(copy)
                        try:
                            src.backup(dst)                      # consistent even while the app writes
                        finally:
                            dst.close()
                            src.close()
                        self.bucket.blob(DB_OBJECT).upload_from_filename(str(copy))
                for folder, prefix in _synced_dirs():
                    if not folder.exists():
                        continue
                    for f in folder.rglob("*"):
                        if not f.is_file():
                            continue
                        key = prefix + f.relative_to(folder).as_posix()
                        mtime = f.stat().st_mtime
                        if self._files.get(key) != mtime:
                            self.bucket.blob(key).upload_from_filename(str(f))
                            self._files[key] = mtime
            except Exception:
                log.exception("Cloud state sync failed (will retry)")

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.sync()

    def start(self) -> None:
        self._db_changed()                                       # the restored state is already saved
        threading.Thread(target=self._run, daemon=True, name="cloud-state-sync").start()

    def stop(self) -> None:
        self._stop.set()
        self.sync()


_syncer: Optional[Syncer] = None


def start(interval: Optional[float] = None) -> Optional[Syncer]:
    global _syncer
    bucket = _bucket()
    if bucket is None or _syncer is not None:
        return _syncer
    _syncer = Syncer(bucket, float(interval or os.getenv("CAM_STATE_SYNC_SECONDS") or 60))
    _syncer.start()
    log.info("Cloud state sync to gs://%s every %ss", bucket.name, _syncer.interval)
    return _syncer


def stop() -> None:
    if _syncer is not None:
        _syncer.stop()
