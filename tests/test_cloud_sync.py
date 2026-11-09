"""Cloud Run state sync (critical fix #2): the database and uploads survive a restart, via a bucket."""

import sqlite3

from src.core import cloud_sync


class FakeBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def exists(self):
        return self.name in self.store

    def download_to_filename(self, path):
        open(path, "wb").write(self.store[self.name])

    def upload_from_filename(self, path):
        self.store[self.name] = open(path, "rb").read()


class FakeBucket:
    name = "test-bucket"

    def __init__(self):
        self.store = {}

    def blob(self, name):
        return FakeBlob(self.store, name)

    def list_blobs(self, prefix=""):
        return [FakeBlob(self.store, n) for n in list(self.store) if n.startswith(prefix)]


def _point_at(monkeypatch, tmp, bucket):
    monkeypatch.setattr(cloud_sync, "RUNTIME_DB_PATH", tmp / "db" / "cam_platform.sqlite3")
    monkeypatch.setattr(cloud_sync, "STORAGE_ROOT", tmp / "storage")
    monkeypatch.setattr(cloud_sync, "DOCUMENTS_ROOT", tmp / "storage" / "documents")
    monkeypatch.setattr(cloud_sync, "_bucket", lambda: bucket)


def test_state_survives_a_restart(tmp_path, monkeypatch):
    bucket = FakeBucket()
    first = tmp_path / "first"
    _point_at(monkeypatch, first, bucket)
    assert cloud_sync.restore() is False                         # empty bucket: the image's demo data is used
    db = cloud_sync.RUNTIME_DB_PATH
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE cases (id TEXT)")
        c.execute("INSERT INTO cases VALUES ('LOS-1')")
    upload = first / "storage" / "flow" / "LOS-1" / "documents" / "board_resolution.pdf"
    prospect = first / "storage" / "documents" / "PDIXON01" / "financials" / "ar.pdf"
    for f in (upload, prospect):
        f.parent.mkdir(parents=True)
        f.write_bytes(b"%PDF-1.4 demo")
    (first / "storage" / "documents" / "INFY001").mkdir()      # catalogue borrowers ship in the image
    (first / "storage" / "documents" / "INFY001" / "x.pdf").write_bytes(b"no")
    syncer = cloud_sync.Syncer(bucket)
    syncer.sync()
    assert set(bucket.store) == {"state/cam_platform.sqlite3", "state/flow/LOS-1/documents/board_resolution.pdf",
                                 "state/documents/PDIXON01/financials/ar.pdf"}
    uploads = dict(bucket.store)
    syncer.sync()                                                # nothing changed: nothing sent again
    assert bucket.store == uploads

    second = tmp_path / "second"                                 # a new instance (restart or redeploy)
    _point_at(monkeypatch, second, bucket)
    assert cloud_sync.restore() is True
    with sqlite3.connect(cloud_sync.RUNTIME_DB_PATH) as c:
        assert c.execute("SELECT id FROM cases").fetchall() == [("LOS-1",)]
    assert (second / "storage" / "flow" / "LOS-1" / "documents" / "board_resolution.pdf").read_bytes() == b"%PDF-1.4 demo"
    assert (second / "storage" / "documents" / "PDIXON01" / "financials" / "ar.pdf").exists()


def test_without_a_bucket_nothing_runs(monkeypatch):
    monkeypatch.delenv("CAM_STATE_BUCKET", raising=False)
    assert cloud_sync.restore() is False and cloud_sync.start() is None
