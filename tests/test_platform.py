"""Governance tests that run against EVERY tool YAML, so a new tool inherits them for free."""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from server.main import ROOT, build_app
from server.seed import seed
from server.spec import ToolSpec, load_directory, load_tools

TOOLS_DIR = ROOT / "tools"


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "test.db"
    seed(db, TOOLS_DIR)
    return TestClient(build_app(TOOLS_DIR, db))


def h(user: str) -> dict:
    return {"X-User": user}


TOOLS = load_tools(TOOLS_DIR)
DIRECTORY = load_directory(TOOLS_DIR)
KNOWN_ROLES = set(DIRECTORY.roles)


# ---- schema-level checks: every YAML must be internally consistent ------------------------
@pytest.mark.parametrize("spec", TOOLS.values(), ids=list(TOOLS))
def test_roles_exist(spec: ToolSpec):
    used = set(spec.permissions.read + spec.permissions.create + spec.permissions.update + spec.permissions.export)
    for a in spec.actions:
        used |= set(a.roles)
    for f in spec.fields:
        used |= set(f.visible_to or [])
    assert used <= KNOWN_ROLES, f"{spec.id} references unknown roles {used - KNOWN_ROLES}"


@pytest.mark.parametrize("spec", TOOLS.values(), ids=list(TOOLS))
def test_export_is_narrower_than_read(spec: ToolSpec):
    assert set(spec.permissions.export) < set(spec.permissions.read), "export must be a strict subset of read"


@pytest.mark.parametrize("spec", TOOLS.values(), ids=list(TOOLS))
def test_destructive_actions_need_comment(spec: ToolSpec):
    for a in spec.actions:
        if a.destructive:
            assert a.requires_comment, f"{spec.id}.{a.id} is destructive but does not require a comment"


def test_invalid_schema_rejected(tmp_path: Path):
    bad = yaml.safe_load((TOOLS_DIR / "kyc_queue.yaml").read_text())
    bad["views"][0]["columns"].append("no_such_field")
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="unknown column"):
        load_tools(tmp_path)


# ---- runtime checks ---------------------------------------------------------------------------
def test_unknown_user_rejected(client):
    assert client.get("/api/me", headers=h("mallory")).status_code == 401


def test_tool_visibility_follows_roles(client):
    tools = {t["id"] for t in client.get("/api/me", headers=h("priya")).json()["tools"]}
    assert tools == {"kyc"}
    tools = {t["id"] for t in client.get("/api/me", headers=h("auditor")).json()["tools"]}
    assert tools == set(TOOLS), "the read-only auditor must be able to see every tool"
    assert client.get("/api/tools/refunds/records", headers=h("priya")).status_code == 403


def test_column_level_security_masks_for_analyst_not_lead(client):
    row = client.get("/api/tools/kyc/records?view=open", headers=h("priya")).json()[0]
    assert row["id_document_number"].startswith("••••") and len(row["id_document_number"]) == 8
    assert row["date_of_birth"] == "••••••"
    lead_row = client.get(f"/api/tools/kyc/records/{row['id']}", headers=h("marcus")).json()
    assert not lead_row["id_document_number"].startswith("•")
    # ...and the analyst cannot write the protected column either
    r = client.patch(f"/api/tools/kyc/records/{row['id']}", json={"id_document_number": "X"}, headers=h("priya"))
    assert r.status_code == 403


def test_keyword_search_does_not_leak_masked_columns(client):
    row = client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json()[0]
    secret = row["id_document_number"]
    assert client.get(f"/api/tools/kyc/records?view=open&q={secret}", headers=h("priya")).json() == []
    assert len(client.get(f"/api/tools/kyc/records?view=open&q={secret}", headers=h("marcus")).json()) == 1


def test_export_privilege(client):
    assert client.get("/api/tools/kyc/records.csv?view=open", headers=h("priya")).status_code == 403
    r = client.get("/api/tools/kyc/records.csv?view=open", headers=h("marcus"))
    assert r.status_code == 200 and r.text.startswith("case_id,")
    assert client.get("/api/tools/kyc/audit", headers=h("marcus")).json()[0]["action"] == "export"


def test_action_roles_guards_and_audit(client):
    pending = client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json()
    case = next(r for r in pending if r["status"] == "Pending")
    rid = case["id"]
    # analyst cannot approve
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("priya")).status_code == 403
    # lead cannot approve a Pending case (state guard)
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("marcus")).status_code == 400
    # analyst starts review, lead approves
    assert client.post("/api/tools/kyc/actions/start_review", json={"record_id": rid}, headers=h("priya")).json()["status"] == "In review"
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("marcus")).json()["status"] == "Approved"
    trail = client.get(f"/api/tools/kyc/audit?record_id={rid}", headers=h("priya")).json()
    assert [e["action"] for e in trail] == ["action:approve", "action:start_review"]
    assert trail[0]["user_id"] == "marcus" and trail[0]["before"] == {"status": "In review"}


def test_reject_requires_comment(client):
    case = next(r for r in client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json() if r["status"] == "In review")
    r = client.post("/api/tools/kyc/actions/reject", json={"record_id": case["id"]}, headers=h("marcus"))
    assert r.status_code == 400 and "comment" in r.json()["detail"]


def test_refund_amount_threshold_routes_to_finance(client):
    large = client.get("/api/tools/refunds/records?view=large", headers=h("dan")).json()[0]
    assert client.post("/api/tools/refunds/actions/approve", json={"record_id": large["id"]}, headers=h("sofia")).status_code == 400
    assert client.post("/api/tools/refunds/actions/approve_large", json={"record_id": large["id"]}, headers=h("sofia")).status_code == 403
    r = client.post("/api/tools/refunds/actions/approve_large", json={"record_id": large["id"], "comment": "ok"}, headers=h("dan"))
    assert r.json()["status"] == "Approved"


def test_webhook_action_logs_integration(client):
    flag = next(r for r in client.get("/api/tools/flags/records?view=all", headers=h("lin")).json() if r["cr_status"] == "None" and not r["prod"])
    rid = flag["id"]
    # engineer: cannot enable PROD without an approved CR, can request one (webhook -> change management)
    assert client.post("/api/tools/flags/actions/enable_prod", json={"record_id": rid}, headers=h("lin")).status_code == 403
    assert client.post("/api/tools/flags/actions/request_release", json={"record_id": rid, "comment": "ship it"}, headers=h("lin")).json()["cr_status"] == "Pending"
    # release manager: approve CR, then enable
    assert client.post("/api/tools/flags/actions/enable_prod", json={"record_id": rid}, headers=h("amara")).status_code == 400
    assert client.post("/api/tools/flags/actions/approve_cr", json={"record_id": rid}, headers=h("amara")).json()["cr_status"] == "Approved"
    assert client.post("/api/tools/flags/actions/enable_prod", json={"record_id": rid}, headers=h("amara")).json()["prod"] == 1
    log = client.get("/api/tools/flags/integrations", headers=h("amara")).json()
    assert log[0]["webhook"].endswith("/flag-store/sync") and log[0]["payload"]["title"] == flag["key"]


def test_dashboard_tiles_compute(client):
    tiles = client.get("/api/tools/refunds/dashboard", headers=h("sofia")).json()
    by_title = {t["title"]: t for t in tiles}
    assert by_title["Refund value (30d)"]["value"] > 0
    assert len(by_title["Refund value by day"]["data"]) == 14
    assert sum(d["value"] for d in by_title["Top refund reasons (30d)"]["data"]) == by_title["Refunds requested (30d)"]["value"]


def test_create_validates_choices_and_required(client):
    r = client.post("/api/tools/refunds/records", json={"merchant": "X", "amount": 5}, headers=h("sofia"))
    assert r.status_code == 400 and "Refund is required" in r.json()["detail"]
    r = client.post("/api/tools/refunds/records", json={"refund_id": "RF-1", "merchant": "X", "amount": 5, "rail": "Cheque"}, headers=h("sofia"))
    assert r.status_code == 400 and "one of" in r.json()["detail"]
    r = client.post("/api/tools/refunds/records", json={"refund_id": "RF-1", "merchant": "X", "amount": "12.5"}, headers=h("sofia"))
    assert r.status_code == 201 and r.json()["status"] == "Awaiting approval" and r.json()["currency"] == "GBP"
