"""Tests for the detailed Airtable results (``src/airtable_results.py``).

HTTP is faked at the ``requests.request`` seam of ``src.airtable_push``
(the shared transport) - no network.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATA_SOURCE", "mock")

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.airtable_push as ap
import src.airtable_results as ar


def _settings(**overrides):
    base = dict(
        airtable_token="pat-test", airtable_base_id="appBASE",
        airtable_results_table="DQ Results",
        airtable_dp_table="Datasets", airtable_dp_match_field="Name",
        airtable_dqr_table="DQRs", airtable_dqr_match_field="Name",
        airtable_cde_table="CDEs", airtable_cde_match_field="Field Name",
        airtable_dp_aliases="SQS=Inspection", airtable_results_field_map="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(**payload_overrides):
    payload = {
        "id": "snap_2026-09-11T22:51:19_SQS", "timestamp": "2026-09-11T22:51:19",
        "source": "auto", "dp_code": "SQS", "dp_name": "SQS_DATA_PRODUCT",
        "overall_score": 99.996, "threshold_green": 80.0, "threshold_yellow": 60.0,
        "total_rows": 935, "rows_green": 930, "rows_yellow": 3, "rows_red": 2,
        "standard_score": None, "custom_score": 99.996,
        "rule_pass_rates": {"STATUS::Completeness": 98.5},
        "custom_rule_pass_rates": {"dq-inspection-12": 100.0},
        "cde_scores": {"STATUS": 100.0, "TOTAL_CONSUMED_HOURS": 87.125},
        "dimension_scores": {"Completeness": 100.0},
        "result_fingerprint": "fp123",
    }
    payload.update(payload_overrides)
    return {"ts": "2026-09-12T01:51:19+00:00", "username": "u@corp.com",
            "domain_code": "quality", "dp_code": "SQS", "config_hash": "cfg1",
            "payload": payload}


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, "ok"
        self.ok = status_code < 400

    def json(self):
        return self._payload


_TABLES = {
    "Datasets": [{"id": "recDP", "fields": {"Name": "Inspection"}},
                 {"id": "recDPadr", "fields": {"Name": "ADR"}}],
    "DQRs": [{"id": "recDQR12", "fields": {"Name": "DQ-Inspection-12"}}],
    "CDEs": [
        # STATUS exists under two Data Products: the DP label breaks the tie.
        {"id": "recCdeSqs", "fields": {"Name": "CDE-Inspection-Status",
                                       "Field Name": "Status"}},
        {"id": "recCdeAdr", "fields": {"Name": "CDE-ADR-Status",
                                       "Field Name": "Status"}},
    ],
}


@pytest.fixture
def airtable(monkeypatch):
    """Configured module + fake transport; returns the list of upsert bodies."""
    settings = _settings()
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setattr(ap, "SETTINGS", settings)
    monkeypatch.setattr(ar.time, "sleep", lambda s: None)
    upserts = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        if method == "GET":
            table = url.split("?")[0].rsplit("/", 1)[-1]
            if _TABLES.get(table) is None:
                return _Resp({"error": "NOT_FOUND"}, status_code=404)
            return _Resp({"records": _TABLES[table]})
        upserts.append(json)
        return _Resp({"records": [{"id": f"rec{len(upserts)}_{i}"}
                                  for i in range(len(json["records"]))]})

    monkeypatch.setattr(ap.requests, "request", MagicMock(side_effect=fake_request))
    return upserts


# ============================================================== build rows

def test_build_rows_one_per_result_with_result_ids():
    rows = ar.build_result_rows(_run())
    run_id = "snap_2026-09-11T22:51:19_SQS"
    assert [r["Result ID"] for r in rows] == [
        f"{run_id}|OVERALL",
        f"{run_id}|DQR|dq-inspection-12",
        f"{run_id}|DQR|status::completeness",
        f"{run_id}|CDE|STATUS",
        f"{run_id}|CDE|TOTAL_CONSUMED_HOURS",
        f"{run_id}|DIMENSION|Completeness",
    ]
    for r in rows:  # every row carries the run columns
        assert r["Run ID"] == run_id
        assert r["Timestamp"] == "2026-09-12T01:51:19+00:00"   # record ts (UTC)
        assert r["Data Product"] == "SQS"
        assert (r["Threshold Green"], r["Threshold Yellow"]) == (80.0, 60.0)


def test_overall_row_carries_buckets_sources_and_run_metadata():
    overall = ar.build_result_rows(_run(standard_score=91.256))[0]
    assert overall["Result Type"] == "OVERALL"
    assert overall["Score"] == pytest.approx(100.0)
    assert (overall["Total Rows"], overall["Green Rows"],
            overall["Yellow Rows"], overall["Red Rows"]) == (935, 930, 3, 2)
    assert overall["Standard Score"] == "91.26"      # single-line-text column
    assert overall["Custom Score"] == pytest.approx(100.0)
    assert overall["Source"] == "auto"
    assert overall["Username"] == "u@corp.com"
    assert overall["Domain Code"] == "quality"
    assert overall["Config Hash"] == "cfg1"
    assert overall["Result Fingerprint"] == "fp123"


def test_absent_values_are_omitted_not_blanked():
    overall = ar.build_result_rows(_run())[0]
    assert "Standard Score" not in overall           # None in the payload
    assert "DQR" not in overall and "Dimension" not in overall


def test_rule_cde_and_dimension_rows():
    rows = {r["Result ID"].split("|", 1)[1]: r for r in ar.build_result_rows(_run())}
    custom = rows["DQR|dq-inspection-12"]
    assert (custom["DQR"], custom["Rule Type"], custom["Score"]) == (
        "dq-inspection-12", "Custom", 100.0)
    standard = rows["DQR|status::completeness"]
    assert (standard["CDE"], standard["Dimension"], standard["Rule Type"]) == (
        "STATUS", "Completeness", "Standard")
    assert "DQR" not in standard
    assert rows["CDE|TOTAL_CONSUMED_HOURS"]["Score"] == pytest.approx(87.12, abs=0.01)
    assert rows["DIMENSION|Completeness"]["Dimension"] == "Completeness"
    assert "Total Rows" not in rows["CDE|STATUS"]


def test_run_without_payload_id_is_rejected():
    with pytest.raises(ap.AirtablePushError, match="payload id"):
        ar.build_result_rows({"payload": {}})


# ==================================================================== push

def test_push_upserts_on_result_id_in_batches_of_ten(airtable):
    cdes = {f"C{i}": 50.0 for i in range(12)}
    summary = ar.push_runs([_run(cde_scores=cdes)])
    sizes = [len(body["records"]) for body in airtable]
    assert sizes == [10, 6]                           # 16 rows total
    assert all(b["performUpsert"] == {"fieldsToMergeOn": ["Result ID"]}
               and b["typecast"] is True for b in airtable)
    assert len(summary.record_ids) == 16
    assert summary.run_ids == ["snap_2026-09-11T22:51:19_SQS"]


def test_links_are_sent_as_record_ids(airtable):
    summary = ar.push_runs([_run()])
    sent = {r["fields"]["Result ID"].split("|", 1)[1]: r["fields"]
            for body in airtable for r in body["records"]}
    # DP alias SQS -> "Inspection"; rule id matched ignoring case.
    assert all(f["Data Product"] == ["recDP"] for f in sent.values())
    assert sent["DQR|dq-inspection-12"]["DQR"] == ["recDQR12"]
    # Two CDE records named "Status": the one mentioning the DP wins.
    assert sent["CDE|STATUS"]["CDE"] == ["recCdeSqs"]
    # No match -> sent empty (clears a stale link) and reported.
    assert sent["CDE|TOTAL_CONSUMED_HOURS"]["CDE"] == []
    assert summary.unresolved == {"CDE": ["TOTAL_CONSUMED_HOURS"]}


def test_links_match_any_text_field_when_no_match_field_is_set(airtable, monkeypatch):
    settings = _settings(airtable_dp_match_field="", airtable_dqr_match_field="",
                         airtable_cde_match_field="")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    summary = ar.push_runs([_run()], dry_run=True)
    rows = {r["Result ID"].split("|", 1)[1]: r for r in summary.rows}
    assert rows["OVERALL"]["Data Product"] == ["recDP"]
    assert rows["DQR|dq-inspection-12"]["DQR"] == ["recDQR12"]
    assert rows["CDE|STATUS"]["CDE"] == ["recCdeSqs"]   # via "Field Name"
    assert summary.unresolved == {"CDE": ["TOTAL_CONSUMED_HOURS"]}


def test_cde_aliases_cover_columns_named_differently_in_airtable(airtable, monkeypatch):
    monkeypatch.setitem(_TABLES, "CDEs", [
        {"id": "recStatus", "fields": {"Name": "CDE-Inspection-Inspection Status",
                                       "Field Name": "Inspection Status"}},
        {"id": "recAllot", "fields": {"Name": "CDE-Inspection-Allotted Hours",
                                      "Field Name": "Allotted Hours"}},
    ])
    summary = ar.push_runs(
        [_run(cde_scores={"STATUS": 100.0, "ALLOTED_HOURS": 90.0, "OTHER": 1.0})],
        dry_run=True)
    rows = {r["Result ID"].split("|", 1)[1]: r for r in summary.rows}
    assert rows["CDE|STATUS"]["CDE"] == ["recStatus"]
    assert rows["CDE|ALLOTED_HOURS"]["CDE"] == ["recAllot"]
    assert summary.unresolved == {"CDE": ["OTHER"]}


def _adr_run(**cdes):
    run = _run(dp_code="ADR", dp_name="ADR_DATA_PRODUCT", cde_scores=cdes,
               rule_pass_rates={}, custom_rule_pass_rates={})
    run["dp_code"] = "ADR"
    return run


def test_cde_of_another_data_product_is_not_linked(airtable, monkeypatch):
    monkeypatch.setitem(_TABLES, "CDEs", [
        {"id": "recSqsPv", "fields": {"Name": "CDE-Inspection-Planview ID",
                                      "Field Name": "Planview ID"}},
        {"id": "recAdrItem", "fields": {"Name": "CDE-ADR-Item Type",
                                        "Field Name": "Item Type"}},
        # No DP in its text, but linked to the ADR record of the DP table.
        {"id": "recAdrQty", "fields": {"Field Name": "Quantity",
                                       "Data Set": ["recDPadr"]}},
    ])
    summary = ar.push_runs(
        [_adr_run(PLANVIEW_ID=1.0, ITEM_TYPE=2.0, QUANTITY=3.0)], dry_run=True)
    rows = {r["Result ID"].split("|", 1)[1]: r for r in summary.rows}
    assert rows["CDE|PLANVIEW_ID"]["CDE"] == []       # only an Inspection CDE
    assert rows["CDE|ITEM_TYPE"]["CDE"] == ["recAdrItem"]
    assert rows["CDE|QUANTITY"]["CDE"] == ["recAdrQty"]
    assert summary.unresolved == {"CDE": ["PLANVIEW_ID"]}


def test_match_field_decides_and_other_fields_are_only_a_fallback(airtable, monkeypatch):
    """Airtable's "Column Name" wins: Cost Basis names COST_UPDATE as its
    column, so the alias pointing COST_BASE_MATERIAL_COST at it is ignored;
    a CDE with no Column Name is still reached through its Field Name."""
    settings = _settings(airtable_cde_match_field="Column Name")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setitem(_TABLES, "CDEs", [
        {"id": "recBasis", "fields": {"Name": "CDE-ADR-Cost Basis",
                                      "Field Name": "Cost Basis",
                                      "Column Name": "COST_UPDATE"}},
        {"id": "recHours", "fields": {"Name": "CDE-ADR-Total Hours",
                                      "Field Name": "Total Hours"}},
        {"id": "recType", "fields": {"Name": "CDE-ADR-Item Type",
                                     "Field Name": "Something else",
                                     "Column Name": "ITEM_TYPE"}},
    ])
    summary = ar.push_runs([_adr_run(
        COST_UPDATE=1.0, COST_BASE_MATERIAL_COST=2.0, COST_TOTAL_HOURS=3.0,
        ITEM_TYPE=4.0)], dry_run=True)
    rows = {r["Result ID"].split("|", 1)[1]: r for r in summary.rows}
    assert rows["CDE|COST_UPDATE"]["CDE"] == ["recBasis"]
    assert rows["CDE|COST_BASE_MATERIAL_COST"]["CDE"] == []
    assert rows["CDE|COST_TOTAL_HOURS"]["CDE"] == ["recHours"]   # alias fallback
    assert rows["CDE|ITEM_TYPE"]["CDE"] == ["recType"]
    assert summary.unresolved == {"CDE": ["COST_BASE_MATERIAL_COST"]}


def test_match_field_may_list_several_column_names(airtable, monkeypatch):
    settings = _settings(airtable_cde_match_field="Column Name")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setitem(_TABLES, "CDEs", [
        {"id": "recDesign", "fields": {
            "Name": "CDE-ADR-Design Parameter",
            "Column Name": "DESIGN_PARAMETER_VALUE, DESIGN_KEY_PARAMETER_NAMES"}},
        {"id": "recMfc", "fields": {"Name": "CDE-ADR-Material Factor Code",
                                    "Column Name": "code\nCOST_BASE_MATERIAL_MFC"}},
    ])
    summary = ar.push_runs([_adr_run(DESIGN_KEY_PARAMETER_NAMES=1.0,
                                     COST_BASE_MATERIAL_MFC=2.0)], dry_run=True)
    rows = {r["Result ID"].split("|", 1)[1]: r for r in summary.rows}
    assert rows["CDE|DESIGN_KEY_PARAMETER_NAMES"]["CDE"] == ["recDesign"]
    assert rows["CDE|COST_BASE_MATERIAL_MFC"]["CDE"] == ["recMfc"]
    assert summary.unresolved == {}


def test_single_match_is_enough_when_the_table_has_no_data_product_info(
        airtable, monkeypatch):
    monkeypatch.setitem(_TABLES, "CDEs", [
        {"id": "recPv", "fields": {"Field Name": "Planview ID"}},
        {"id": "recIt", "fields": {"Field Name": "Item Type"}},
    ])
    summary = ar.push_runs([_adr_run(PLANVIEW_ID=1.0)], dry_run=True)
    assert summary.rows[1]["CDE"] == ["recPv"]
    assert summary.unresolved == {}


def test_link_table_alternative_names_first_existing_wins(airtable, monkeypatch):
    settings = _settings(airtable_dp_table="Data Sets|Datasets")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    real = ap.requests.request.side_effect

    def fake(method, url, **kwargs):
        if method == "GET" and "/Data%20Sets?" in url:
            return _Resp({"error": "NOT_FOUND"}, status_code=404)
        return real(method, url, **kwargs)

    monkeypatch.setattr(ap.requests, "request", MagicMock(side_effect=fake))
    summary = ar.push_runs([_run()], dry_run=True)
    assert summary.rows[0]["Data Product"] == ["recDP"]

    settings = _settings(airtable_dp_table="Data Sets|Nope")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setitem(_TABLES, "Nope", None)
    with pytest.raises(ap.AirtablePushError):
        ar.push_runs([_run()], dry_run=True)


def test_unconfigured_link_table_leaves_the_link_blank(airtable, monkeypatch):
    settings = _settings(airtable_cde_table="", airtable_dqr_table="")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    summary = ar.push_runs([_run()])
    fields = [r["fields"] for body in airtable for r in body["records"]]
    assert all("CDE" not in f and "DQR" not in f for f in fields)
    assert summary.unresolved == {}
    gets = [c for c in ap.requests.request.call_args_list if c[0][0] == "GET"]
    assert len(gets) == 1 and "/Datasets?" in gets[0][0][1]


def test_field_map_renames_and_drops_columns(airtable, monkeypatch):
    settings = _settings(airtable_results_field_map=json.dumps(
        {"Green Rows": "Green rows", "Username": "", "Result ID": "fldKEY"}))
    monkeypatch.setattr(ar, "SETTINGS", settings)
    ar.push_runs([_run()])
    overall = airtable[0]["records"][0]["fields"]
    assert overall["Green rows"] == 930 and "Green Rows" not in overall
    assert "Username" not in overall
    assert airtable[0]["performUpsert"] == {"fieldsToMergeOn": ["fldKEY"]}


def test_link_table_pagination_follows_offset(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setattr(ap, "SETTINGS", settings)
    monkeypatch.setattr(ar.time, "sleep", lambda s: None)
    pages = [
        _Resp({"records": [{"id": "rec1", "fields": {"Name": "A"}}], "offset": "o1"}),
        _Resp({"records": [{"id": "rec2", "fields": {"Name": "B"}}]}),
    ]
    fake = MagicMock(side_effect=pages)
    monkeypatch.setattr(ap.requests, "request", fake)
    index = ar._load_link_index("Datasets", "Name")
    assert [rec[0] for rec in index] == ["rec1", "rec2"]
    assert "offset=o1" in fake.call_args_list[1][0][1]


def test_push_requires_configuration_and_runs(monkeypatch):
    settings = _settings(airtable_token="")
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setattr(ap, "SETTINGS", settings)
    assert ar.is_configured() is False
    with pytest.raises(ap.AirtablePushError, match="not configured"):
        ar.push_runs([_run()])
    settings = _settings()
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setattr(ap, "SETTINGS", settings)
    with pytest.raises(ap.AirtablePushError, match="No persisted run"):
        ar.push_runs([])


def test_push_latest_runs_reads_the_newest_persisted_run(airtable):
    from src.persistence import save_run

    save_run("SQS", "quality", _run()["payload"] | {"id": "snap_old_SQS"}, "c0")
    save_run("SQS", "quality", _run()["payload"], "c1")
    summary = ar.push_latest_runs(["SQS", "ADR"])     # ADR never ran: skipped
    assert summary.run_ids == ["snap_2026-09-11T22:51:19_SQS"]
    with pytest.raises(ap.AirtablePushError, match="No persisted run"):
        ar.push_latest_runs(["ADR"])


def test_dry_run_resolves_links_but_writes_nothing(airtable):
    summary = ar.push_runs([_run()], dry_run=True)
    assert airtable == [] and summary.record_ids == []
    assert len(summary.rows) == 6
    assert summary.rows[0]["Data Product"] == ["recDP"]
    assert summary.unresolved == {"CDE": ["TOTAL_CONSUMED_HOURS"]}


def test_inspect_schema_reports_missing_computed_and_link_targets(monkeypatch):
    settings = _settings(airtable_results_field_map=json.dumps({"Username": ""}))
    monkeypatch.setattr(ar, "SETTINGS", settings)
    monkeypatch.setattr(ap, "SETTINGS", settings)
    schema = {"tables": [
        {"id": "tblRES", "name": "DQ Results", "primaryFieldId": "f1", "fields": [
            {"id": "f1", "name": "Result ID", "type": "multilineText"},
            {"id": "f2", "name": "Score", "type": "formula"},
            {"id": "f3", "name": "Data Product", "type": "multipleRecordLinks",
             "options": {"linkedTableId": "tblDS"}},
            {"id": "f4", "name": "Green rows", "type": "number"},
        ]},
        {"id": "tblDS", "name": "Datasets", "primaryFieldId": "d1", "fields": [
            {"id": "d1", "name": "Dataset Name", "type": "singleLineText"},
            {"id": "d2", "name": "Owner", "type": "singleLineText"},
        ]},
    ]}
    monkeypatch.setattr(ap.requests, "request",
                        MagicMock(return_value=_Resp(schema)))
    report = ar.inspect_schema()
    assert report["computed"] == ["Score"]
    assert "Green Rows" in report["missing"]          # exists as "Green rows"
    assert "Username" not in report["missing"]        # dropped by the field map
    assert report["types"]["Result ID"] == "multilineText"
    assert report["links"] == {"Data Product": {
        "table": "Datasets", "primary_field": "Dataset Name",
        "fields": ["Dataset Name", "Owner"]}}

    monkeypatch.setattr(ar, "SETTINGS", _settings(airtable_results_table="Nope"))
    with pytest.raises(ap.AirtablePushError, match="not found in the base"):
        ar.inspect_schema()


# ================================================================ UI button

def test_button_also_pushes_detailed_results(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "is_configured", lambda: True)
    monkeypatch.setattr(ap, "push_results", lambda *a, **k: ["recA"])
    monkeypatch.setattr(ar, "is_configured", lambda: True)
    monkeypatch.setattr(ar, "push_latest_runs", lambda codes: ar.ResultsPushSummary(
        record_ids=["r1", "r2"], run_ids=["snap_x"],
        unresolved={"CDE": ["PLANVIEW_ID"]}))
    events = []
    monkeypatch.setattr(er, "log_event", lambda *a, **k: events.append(a))
    fake_st = MagicMock()
    fake_st.button.return_value = True
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", {"EPT": object()})
    assert fake_st.success.call_count == 2
    assert "PLANVIEW_ID" in fake_st.warning.call_args[0][0]
    assert [e[1]["format"] for e in events] == ["airtable_push", "airtable_results"]
