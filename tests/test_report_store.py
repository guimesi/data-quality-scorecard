"""Tests for the report store (``src/report_store.py``): local files,
Unity Catalog Volume (faked Files API), off, run-id validation and the
fire-and-forget contract."""
from __future__ import annotations

import io
import json
import os

os.environ.setdefault("DATA_SOURCE", "mock")

import pytest

from config.settings import Settings
from src import report_store as rs
from ui.step_06.report.models import ReportArtifacts


def _artifacts(run_id: str = "run_20260910_120000_ab12", pdf=b"%PDF-1.7 x"):
    return ReportArtifacts(
        run_id=run_id, domain_code="cost_estimate",
        generated_at="2026-09-10T12:00:00Z",
        html=b"<!DOCTYPE html><html>interactive</html>", pdf=pdf,
        pdf_html=b"<!DOCTYPE html><html>print</html>",
        metadata={"dp_codes": ["EPT"], "overall_scores": {"EPT": 81.5},
                  "statuses": {"EPT": "green"}, "generated_by": "tester",
                  "domain_name": "Cost Estimate"},
        filenames={"interactive": "dq_scorecard_report_X.html",
                   "pdf": "dq_scorecard_report_X.pdf",
                   "pdf_html": "dq_scorecard_report_X_print.html"},
    )


@pytest.fixture
def local_store(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="local", store_dir=str(tmp_path)))
    rs.reset_report_store()
    yield tmp_path / "reports"
    rs.reset_report_store()


# ------------------------------------------------------------ validation

@pytest.mark.parametrize("bad", [
    "", "../x", "a/b", "run id", "x" * 81, None, 42, ".hidden", "-lead",
])
def test_invalid_run_ids_rejected(bad):
    assert not rs.is_valid_run_id(bad)


@pytest.mark.parametrize("good", ["run_20260910_120000_ab12", "abc", "A-1_b"])
def test_valid_run_ids(good):
    assert rs.is_valid_run_id(good)


def test_load_never_touches_storage_for_bad_ids(local_store):
    assert rs.load_report("../../etc/passwd") is None
    assert rs.load_report("ok-id", kind="nope") is None
    assert rs.load_metadata("a b") is None


# ------------------------------------------------------------------ local

def test_local_roundtrip_and_listing(local_store):
    art = _artifacts()
    assert rs.save_artifacts(art) is True
    names = sorted(p.name for p in local_store.iterdir())
    assert names == [
        f"{art.run_id}.html", f"{art.run_id}.json", f"{art.run_id}.pdf",
        f"{art.run_id}.print.html",
    ]
    assert rs.load_report(art.run_id) == art.html
    assert rs.load_report(art.run_id, "pdf") == art.pdf
    assert rs.load_report(art.run_id, "pdf_html") == art.pdf_html
    meta = rs.load_metadata(art.run_id)
    assert meta["run_id"] == art.run_id
    assert meta["has_pdf"] is True
    assert meta["filenames"]["pdf"] == "dq_scorecard_report_X.pdf"
    assert meta["overall_scores"] == {"EPT": 81.5}
    assert rs.load_report("run_unknown") is None
    assert rs.is_enabled()

    # Listing is newest first and only reads valid run ids.
    older = _artifacts(run_id="run_20260101_000000_old", pdf=None)
    rs.save_artifacts(ReportArtifacts(
        **{**older.__dict__, "generated_at": "2026-01-01T00:00:00Z"}))
    (local_store / "junk.json").write_text("{}")
    (local_store / "bad id.json").write_text("{}")
    listing = rs.list_reports()
    assert [m["run_id"] for m in listing] == [art.run_id, older.run_id]
    assert listing[1]["has_pdf"] is False
    assert rs.load_report(older.run_id, "pdf") is None


def test_save_refuses_invalid_run_id(local_store):
    art = _artifacts(run_id="../escape")
    assert rs.save_artifacts(art) is False
    assert not local_store.exists()


def test_write_failures_are_swallowed(local_store, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(rs.LocalReportStore, "put", boom)
    assert rs.save_artifacts(_artifacts()) is False
    monkeypatch.setattr(rs.LocalReportStore, "get", boom)
    assert rs.load_report("run_x") is None
    monkeypatch.setattr(rs.LocalReportStore, "list_run_ids", boom)
    assert rs.list_reports() == []


def test_report_url():
    assert rs.report_url("run_1") == "/reports/run_1"
    assert rs.report_url("run_1", "pdf") == "/reports/run_1/pdf"


# -------------------------------------------------------------------- off

def test_off_backend_stores_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="off", store_dir=str(tmp_path)))
    rs.reset_report_store()
    try:
        assert isinstance(rs.get_report_store(), rs.NullReportStore)
        assert not rs.is_enabled()
        assert rs.save_artifacts(_artifacts()) is False
        assert rs.load_report("run_20260910_120000_ab12") is None
        assert rs.list_reports() == []
        assert not (tmp_path / "reports").exists()
    finally:
        rs.reset_report_store()


def test_unknown_backend_falls_back_to_local(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="s3", store_dir=str(tmp_path)))
    rs.reset_report_store()
    try:
        assert isinstance(rs.get_report_store(), rs.LocalReportStore)
    finally:
        rs.reset_report_store()


def test_volume_backend_without_path_degrades_to_off(monkeypatch):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="volume", report_volume_path=""))
    rs.reset_report_store()
    try:
        assert isinstance(rs.get_report_store(), rs.NullReportStore)
    finally:
        rs.reset_report_store()


# ----------------------------------------------------------------- volume

class _Entry:
    def __init__(self, name):
        self.name = name


class _Download:
    def __init__(self, data):
        self.contents = io.BytesIO(data)


class _FakeFiles:
    """Just enough of ``WorkspaceClient().files`` for the store."""

    def __init__(self):
        self.objects = {}
        self.dirs = []

    def create_directory(self, path):
        self.dirs.append(path)

    def upload(self, path, contents, overwrite=None):
        assert overwrite is True
        self.objects[path] = contents.read()

    def download(self, path):
        from databricks.sdk.errors import NotFound
        if path not in self.objects:
            raise NotFound("nope")
        return _Download(self.objects[path])

    def list_directory_contents(self, path):
        from databricks.sdk.errors import NotFound
        if path not in self.dirs:
            raise NotFound("nope")
        prefix = path + "/"
        return [_Entry(p[len(prefix):]) for p in self.objects if p.startswith(prefix)]


class _FakeClient:
    def __init__(self):
        self.files = _FakeFiles()


def test_volume_store_roundtrip_via_files_api():
    client = _FakeClient()
    store = rs.VolumeReportStore(
        "/Volumes/cat/schema/dq_reports/", client=client)
    art = _artifacts()
    store.put(art.run_id, "html", art.html)
    store.put(art.run_id, "metadata", json.dumps({"run_id": art.run_id}).encode())
    assert client.files.dirs == ["/Volumes/cat/schema/dq_reports"] * 2
    assert store.get(art.run_id, "html") == art.html
    assert store.get(art.run_id, "pdf") is None
    assert store.list_run_ids() == [art.run_id]
    assert "/Volumes/cat/schema/dq_reports/run_20260910_120000_ab12.html" \
        in client.files.objects


def test_volume_store_requires_a_volume_path():
    with pytest.raises(ValueError):
        rs.VolumeReportStore("/tmp/not-a-volume")
    with pytest.raises(ValueError):
        rs.VolumeReportStore("")


def test_volume_store_is_selected_by_settings(monkeypatch):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="volume",
        report_volume_path="/Volumes/cat/schema/dq_reports"))
    rs.reset_report_store()
    try:
        store = rs.get_report_store()
        assert isinstance(store, rs.VolumeReportStore)
        assert store.directory == "/Volumes/cat/schema/dq_reports"
        # Storage errors from the SDK never escape the domain API.
        fake = _FakeClient()

        def explode(*a, **k):
            raise RuntimeError("no network")
        fake.files.upload = explode
        store._client = fake
        assert rs.save_artifacts(_artifacts()) is False
        assert rs.load_report("run_20260910_120000_ab12") is None
    finally:
        rs.reset_report_store()
