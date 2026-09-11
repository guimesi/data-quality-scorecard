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


def _artifacts(run_id: str = "run_20260910_120000_ab12", pdf=b"%PDF-1.7 x",
               domain_code: str = "cost_estimate",
               generated_at: str = "2026-09-10T12:00:00Z"):
    return ReportArtifacts(
        run_id=run_id, domain_code=domain_code,
        generated_at=generated_at,
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
    def __init__(self, name, is_directory=False):
        self.name = name
        self.is_directory = is_directory


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
        out = [_Entry(p[len(prefix):]) for p in self.objects
               if p.startswith(prefix) and "/" not in p[len(prefix):]]
        out += [_Entry(d[len(prefix):], is_directory=True) for d in self.dirs
                if d.startswith(prefix) and "/" not in d[len(prefix):]]
        return out


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
    assert "/Volumes/cat/schema/dq_reports/run_20260910_120000_ab12.html" \
        in client.files.objects
    # A minted id is filed under its domain folder; listing covers both.
    minted = "COST_ESTIMATE__EPT__20260911_120000_ab12"
    store.put(minted, "metadata", json.dumps({"run_id": minted}).encode())
    assert client.files.dirs[-1] == "/Volumes/cat/schema/dq_reports/COST_ESTIMATE"
    assert f"/Volumes/cat/schema/dq_reports/COST_ESTIMATE/{minted}.json" \
        in client.files.objects
    assert store.list_run_ids() == [minted, art.run_id]


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


# ============================================================ workspace files


class _WsObj:
    def __init__(self, path):
        self.path = path
        self.object_type = "FILE"


class _FakeWorkspace:
    """Just enough of ``WorkspaceClient().workspace`` for the store."""

    def __init__(self):
        self.objects = {}
        self.dirs = []
        self.uploads = []

    def mkdirs(self, path):
        self.dirs.append(path)

    def upload(self, path, content, format=None, overwrite=False):
        assert overwrite is True and format is not None and format.value == "AUTO"
        self.uploads.append(path)
        self.objects[path] = content.read()

    def download(self, path, format=None):
        from databricks.sdk.errors import NotFound
        assert format is not None and format.value == "AUTO"
        if path not in self.objects:
            raise NotFound("nope")
        return io.BytesIO(self.objects[path])

    def list(self, path, recursive=False):
        from databricks.sdk.errors import NotFound
        if path not in self.dirs:
            raise NotFound("nope")
        return [_WsObj(p) for p in self.objects if p.startswith(path + "/")
                and (recursive or "/" not in p[len(path) + 1:])]

    def delete(self, path, recursive=None):
        from databricks.sdk.errors import NotFound
        if path not in self.objects:
            raise NotFound("nope")
        del self.objects[path]


class _FakeWsClient:
    def __init__(self):
        self.workspace = _FakeWorkspace()


@pytest.mark.parametrize("given, api_path", [
    ("/Workspace/Users/ana@corp.com/dq_reports", "/Users/ana@corp.com/dq_reports"),
    ("/Users/ana@corp.com/dq_reports/", "/Users/ana@corp.com/dq_reports"),
    ("/Workspace/Shared/dq_reports", "/Shared/dq_reports"),
])
def test_workspace_store_accepts_browser_and_api_paths(given, api_path):
    assert rs.WorkspaceReportStore(given, client=_FakeWsClient()).directory == api_path


@pytest.mark.parametrize("bad", ["", "/tmp/x", "/Volumes/c/s/v", "/Users", "Users/x/y"])
def test_workspace_store_rejects_non_workspace_paths(bad):
    with pytest.raises(ValueError):
        rs.WorkspaceReportStore(bad, client=_FakeWsClient())


def test_workspace_store_roundtrip_via_workspace_api():
    client = _FakeWsClient()
    store = rs.WorkspaceReportStore("/Workspace/Users/ana@corp.com/dq_reports",
                                    client=client)
    art = _artifacts()
    store.put(art.run_id, "html", art.html)
    store.put(art.run_id, "metadata", json.dumps({"run_id": art.run_id}).encode())
    assert client.workspace.dirs == ["/Users/ana@corp.com/dq_reports"]  # mkdirs once
    assert client.workspace.uploads[0] == \
        "/Users/ana@corp.com/dq_reports/run_20260910_120000_ab12.html"
    minted = "COST_ESTIMATE__ACCE-ADR__20260911_120000_ab12"
    store.put(minted, "pdf", b"%PDF")
    store.put(minted, "metadata", json.dumps({"run_id": minted}).encode())
    assert client.workspace.dirs == ["/Users/ana@corp.com/dq_reports",
                                     "/Users/ana@corp.com/dq_reports/COST_ESTIMATE"]
    assert client.workspace.uploads[-1] == \
        f"/Users/ana@corp.com/dq_reports/COST_ESTIMATE/{minted}.json"
    assert store.get(minted, "pdf") == b"%PDF"
    assert store.list_run_ids() == [minted, art.run_id]
    assert store.get(art.run_id, "html") == art.html
    assert store.get(art.run_id, "pdf") is None
    assert store.list_run_ids() == [minted, art.run_id]
    store.delete(art.run_id, "html")
    store.delete(art.run_id, "html")            # already gone: no error
    assert store.get(art.run_id, "html") is None


def test_workspace_store_refuses_files_over_the_api_limit():
    store = rs.WorkspaceReportStore("/Users/ana@corp.com/dq_reports",
                                    client=_FakeWsClient())
    with pytest.raises(ValueError, match="10 MB"):
        store.put("run_1", "pdf", b"x" * (rs.WorkspaceReportStore.MAX_BYTES + 1))


def test_workspace_backend_selected_and_failures_swallowed(monkeypatch):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="workspace",
        report_workspace_dir="/Workspace/Users/ana@corp.com/dq_reports"))
    rs.reset_report_store()
    try:
        store = rs.get_report_store()
        assert isinstance(store, rs.WorkspaceReportStore)
        store._client = _FakeWsClient()
        assert rs.save_artifacts(_artifacts()) is True
        assert rs.load_report("run_20260910_120000_ab12") == _artifacts().html
        assert rs.latest_run_id("cost_estimate") == "run_20260910_120000_ab12"

        def explode(*a, **k):
            raise RuntimeError("no network")
        store._client.workspace.upload = explode
        assert rs.save_artifacts(_artifacts(run_id="run_other")) is False
    finally:
        rs.reset_report_store()


def test_workspace_backend_without_dir_degrades_to_off(monkeypatch):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="workspace", report_workspace_dir=""))
    rs.reset_report_store()
    try:
        assert isinstance(rs.get_report_store(), rs.NullReportStore)
        assert rs.is_enabled() is False
    finally:
        rs.reset_report_store()


# ================================================================ retention


def _stored(monkeypatch, tmp_path, keep):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="local", store_dir=str(tmp_path),
        report_keep_runs=keep))
    rs.reset_report_store()


def test_prune_keeps_newest_n_per_domain(monkeypatch, tmp_path):
    _stored(monkeypatch, tmp_path, keep=2)
    try:
        for i, (domain, stamp) in enumerate([
            ("cost_estimate", "2026-09-01T10:00:00Z"),
            ("cost_estimate", "2026-09-02T10:00:00Z"),
            ("quality", "2026-09-02T11:00:00Z"),
            ("cost_estimate", "2026-09-03T10:00:00Z"),
        ]):
            rs.save_artifacts(_artifacts(run_id=f"run_{i}", domain_code=domain,
                                         generated_at=stamp))
        ids = {m["run_id"] for m in rs.list_reports()}
        assert ids == {"run_1", "run_3", "run_2"}        # run_0 pruned
        assert rs.load_report("run_0") is None
        assert not (tmp_path / "reports" / "run_0.pdf").exists()
        assert rs.latest_run_id("COST_ESTIMATE") == "run_3"
        assert rs.latest_run_id("quality") == "run_2"
        assert rs.latest_run_id("nope") is None
    finally:
        rs.reset_report_store()


def test_prune_disabled_with_zero(monkeypatch, tmp_path):
    _stored(monkeypatch, tmp_path, keep=0)
    try:
        for i in range(3):
            rs.save_artifacts(_artifacts(run_id=f"run_{i}",
                                         generated_at=f"2026-09-0{i + 1}T10:00:00Z"))
        assert len(rs.list_reports()) == 3
        assert rs.prune_reports() == []
        assert rs.prune_reports(keep=1) == ["run_1", "run_0"]
    finally:
        rs.reset_report_store()


def test_last_error_and_describe_store(monkeypatch, tmp_path):
    _stored(monkeypatch, tmp_path, keep=0)
    try:
        assert rs.save_artifacts(_artifacts()) is True
        assert rs.last_error() is None
        assert rs.describe_store() == f"local folder {tmp_path / 'reports'}"

        def explode(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(rs.get_report_store(), "put", explode)
        assert rs.save_artifacts(_artifacts(run_id="run_x")) is False
        assert rs.last_error() == "OSError: disk full"
    finally:
        rs.reset_report_store()
    ws = rs.WorkspaceReportStore("/Workspace/Users/ana@corp.com/dq_reports",
                                 client=_FakeWsClient())
    monkeypatch.setattr(rs, "_STORE", ws)
    assert rs.describe_store() == "workspace folder /Users/ana@corp.com/dq_reports"
    rs.reset_report_store()


def test_local_store_files_minted_runs_per_domain(monkeypatch, tmp_path):
    _stored(monkeypatch, tmp_path, keep=0)
    try:
        minted = "QUALITY__SQS__20260911_120000_ab12"
        assert rs.save_artifacts(_artifacts(run_id=minted, domain_code="quality"))
        assert rs.save_artifacts(_artifacts())                 # legacy id: root
        root = tmp_path / "reports"
        assert (root / "QUALITY" / f"{minted}.html").is_file()
        assert (root / "QUALITY" / f"{minted}.pdf").is_file()
        assert (root / "run_20260910_120000_ab12.html").is_file()
        assert rs.load_report(minted, "pdf") == b"%PDF-1.7 x"
        assert sorted(m["run_id"] for m in rs.list_reports()) == \
            [minted, "run_20260910_120000_ab12"]
        assert rs.prune_reports(keep=1) == []                  # one per domain
        rs.get_report_store().delete(minted, "html")
        assert not (root / "QUALITY" / f"{minted}.html").exists()
    finally:
        rs.reset_report_store()


@pytest.mark.parametrize("run_id, folder", [
    ("COST_ESTIMATE__ACCE-ADR__20260911_120000_ab12", "COST_ESTIMATE"),
    ("run_20260910_120000_ab12", ""),
    ("__x", ""),
])
def test_run_folder(run_id, folder):
    assert rs.run_folder(run_id) == folder


def test_latest_url_shapes():
    assert rs.latest_url("cost_estimate") == "/reports/latest/COST_ESTIMATE"
    assert rs.latest_url("cost_estimate", "pdf") == "/reports/latest/COST_ESTIMATE/pdf"
