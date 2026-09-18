"""Governance tests that run against EVERY tool YAML, so a new tool inherits them for free."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from server.ai import RulesProvider
from server.kb import LexicalEmbedder
from server.main import ROOT, build_app
from server.seed import seed
from server.spec import ToolSpec, load_directory, load_tools

TOOLS_DIR = ROOT / "tools"


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "test.db"
    seed(db, TOOLS_DIR)
    # tests never call an LLM or an embeddings API
    return TestClient(build_app(TOOLS_DIR, db, provider=RulesProvider(), embedder=LexicalEmbedder()))


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
    tools = {t["id"] for t in client.get("/api/me", headers=h("lin")).json()["tools"]}
    assert tools == {"flags"}
    assert client.get("/api/tools/refunds/records", headers=h("priya")).status_code == 403


def test_no_single_person_sees_every_board(client):
    all_apps = {t.app for t in TOOLS.values()}
    for u in client.get("/api/users").json():
        apps = {t["app"] for t in client.get("/api/me", headers=h(u["id"])).json()["tools"]}
        assert apps and apps < all_apps, f"{u['name']} would see every board: {apps}"


def test_service_account_cannot_sign_in(client):
    assert "devin-ai" not in {u["id"] for u in client.get("/api/users").json()}
    assert client.get("/api/me", headers=h("devin-ai")).status_code == 401


def test_system_actions_hidden_from_humans(client):
    tool = client.get("/api/tools/kyc", headers=h("marcus")).json()
    assert "auto_approve" not in {a["id"] for a in tool["actions"]}
    case = client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json()[0]
    assert client.post("/api/tools/kyc/actions/auto_approve", json={"record_id": case["id"]}, headers=h("marcus")).status_code == 403


def test_open_queue_is_high_risk_first(client):
    scores = [r["risk_score"] for r in client.get("/api/tools/kyc/records?view=open", headers=h("priya")).json()]
    assert scores == sorted(scores, reverse=True) and scores[0] >= 70


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
    case = next(r for r in pending if r["status"] == "Pending" and r["policy_verdict"] == "Cleared")
    rid = case["id"]
    # read-only has no right to act at all
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("auditor")).status_code == 403
    # analyst starts review, lead approves
    assert client.post("/api/tools/kyc/actions/start_review", json={"record_id": rid}, headers=h("priya")).json()["status"] == "In review"
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("marcus")).json()["status"] == "Approved"
    # state guard: nothing left to decide
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("marcus")).status_code == 400
    trail = client.get(f"/api/tools/kyc/audit?record_id={rid}", headers=h("priya")).json()
    assert [e["action"] for e in trail] == ["action:approve", "action:start_review"]
    assert trail[0]["user_id"] == "marcus" and trail[0]["before"] == {"status": "In review"}
    assert "policy override" not in (trail[0]["comment"] or "")


def test_decisions_outside_four_eyes_role_warn_then_audit_the_override(client):
    """KYC-1.2: approvals are a compliance-lead decision. An analyst is not blocked - the preview
    tells the UI which clauses would be overridden, and the run writes them into the audit comment."""
    case = next(r for r in client.get("/api/tools/kyc/records?view=open", headers=h("priya")).json()
                if r["status"] == "In review" and r["policy_verdict"] == "Cleared")
    rid = case["id"]
    preview = client.get("/api/tools/kyc/actions/approve/preview", params={"record_id": rid}, headers=h("priya")).json()
    assert [o["clause"] for o in preview["overrides"]] == ["KYC-1.2"]
    assert preview["overrides"][0]["clause_text"] and preview["overrides"][0]["policy"] == "kyc_review_policy"
    # the lead has nothing to override on a clean case
    assert client.get("/api/tools/kyc/actions/approve/preview", params={"record_id": rid}, headers=h("marcus")).json()["overrides"] == []
    # read-only cannot even preview
    assert client.get("/api/tools/kyc/actions/approve/preview", params={"record_id": rid}, headers=h("auditor")).status_code == 403
    assert client.post("/api/tools/kyc/actions/approve", json={"record_id": rid}, headers=h("priya")).json()["status"] == "Approved"
    trail = client.get(f"/api/tools/kyc/audit?record_id={rid}", headers=h("marcus")).json()
    assert trail[0]["user_id"] == "priya" and "policy override" in trail[0]["comment"] and "KYC-1.2" in trail[0]["comment"]


def test_approving_a_record_with_failing_checks_lists_the_failed_clauses(client):
    case = next(r for r in client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json()
                if r["status"] in ("In review", "Escalated") and r["sanctions_hit"])
    preview = client.get("/api/tools/kyc/actions/approve/preview", params={"record_id": case["id"]}, headers=h("marcus")).json()
    clauses = {o["clause"] for o in preview["overrides"]}
    assert "KYC-2.1" in clauses and "KYC-1.2" not in clauses
    # rejecting the same record overrides nothing: failing checks only matter for approvals
    assert client.get("/api/tools/kyc/actions/reject/preview", params={"record_id": case["id"]}, headers=h("marcus")).json()["overrides"] == []
    client.post("/api/tools/kyc/actions/approve", json={"record_id": case["id"], "comment": "EDD completed offline"}, headers=h("marcus"))
    trail = client.get(f"/api/tools/kyc/audit?record_id={case['id']}", headers=h("marcus")).json()
    assert trail[0]["comment"].startswith("EDD completed offline") and "KYC-2.1" in trail[0]["comment"]


def test_reject_requires_comment(client):
    case = next(r for r in client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json() if r["status"] == "In review")
    r = client.post("/api/tools/kyc/actions/reject", json={"record_id": case["id"]}, headers=h("marcus"))
    assert r.status_code == 400 and "comment" in r.json()["detail"]


def test_refund_amount_threshold_routes_to_finance(client):
    large = client.get("/api/tools/refunds/records?view=large", headers=h("dan")).json()[0]
    assert client.post("/api/tools/refunds/actions/approve", json={"record_id": large["id"]}, headers=h("sofia")).status_code == 400
    # ops may approve a large refund, but only with a justification, and RF-1.2 is flagged as overridden
    assert client.post("/api/tools/refunds/actions/approve_large", json={"record_id": large["id"]}, headers=h("sofia")).status_code == 400
    preview = client.get("/api/tools/refunds/actions/approve_large/preview", params={"record_id": large["id"]}, headers=h("sofia")).json()
    assert "RF-1.2" in {o["clause"] for o in preview["overrides"]}
    assert "RF-1.2" not in {o["clause"] for o in client.get("/api/tools/refunds/actions/approve_large/preview", params={"record_id": large["id"]}, headers=h("dan")).json()["overrides"]}
    r = client.post("/api/tools/refunds/actions/approve_large", json={"record_id": large["id"], "comment": "ok"}, headers=h("dan"))
    assert r.json()["status"] == "Approved"


def test_webhook_action_logs_integration(client):
    flag = next(r for r in client.get("/api/tools/flags/records?view=all", headers=h("lin")).json() if r["cr_status"] == "None" and not r["prod"])
    rid = flag["id"]
    # engineer toggles PROD directly (webhook -> flag store); FF-2.1 is enforced by the policy check, not the toggle
    assert client.post("/api/tools/flags/actions/enable_prod", json={"record_id": rid}, headers=h("lin")).json()["prod"] == 1
    log = client.get("/api/tools/flags/integrations", headers=h("lin")).json()
    assert log[0]["webhook"].endswith("/flag-store/sync") and log[0]["payload"]["title"] == flag["key"]
    review = client.get(f"/api/tools/flags/records/{rid}/review", headers=h("lin")).json()
    assert review["verdict"] == "Flagged" and any(c["clause"] == "FF-2.1" and not c["passed"] for c in review["checks"])
    # kill switch is open to engineers too, but needs a comment
    assert client.post("/api/tools/flags/actions/kill_switch", json={"record_id": rid}, headers=h("lin")).status_code == 400
    assert client.post("/api/tools/flags/actions/kill_switch", json={"record_id": rid, "comment": "rollback"}, headers=h("lin")).json()["prod"] == 0
    # CRs are raised outside this tool (no request action); an engineer approving one is warned (FF-2.2) and audited
    assert "request_release" not in {a["id"] for a in client.get("/api/tools/flags", headers=h("lin")).json()["actions"]}
    pending = next(r for r in client.get("/api/tools/flags/records?view=all", headers=h("lin")).json() if r["cr_status"] == "Pending")
    assert [o["clause"] for o in client.get("/api/tools/flags/actions/approve_cr/preview", params={"record_id": pending["id"]}, headers=h("lin")).json()["overrides"]] == ["FF-2.2"]
    assert client.get("/api/tools/flags/actions/approve_cr/preview", params={"record_id": pending["id"]}, headers=h("amara")).json()["overrides"] == []
    assert client.post("/api/tools/flags/actions/approve_cr", json={"record_id": pending["id"]}, headers=h("amara")).json()["cr_status"] == "Approved"
    assert client.post("/api/tools/flags/actions/enable_prod", json={"record_id": pending["id"]}, headers=h("lin")).json()["prod"] == 1
    review = client.get(f"/api/tools/flags/records/{pending['id']}/review", headers=h("lin")).json()
    assert all(c["passed"] for c in review["checks"] if c["clause"] == "FF-2.1")


def test_webhook_payloads_are_signed_with_env_secret_only(client, monkeypatch):
    """The signing secret lives in the environment (Devin secrets / deployment secret manager),
    never in YAML, seed data or source. Without it, payloads are explicitly marked unsigned."""
    monkeypatch.delenv("WEBHOOK_SIGNING_SECRET", raising=False)
    refund = client.get("/api/tools/refunds/records?view=approved", headers=h("dan")).json()[0]
    unsigned = client.post("/api/tools/refunds/actions/pay", json={"record_id": refund["id"], "comment": "release"}, headers=h("dan"))
    assert unsigned.status_code == 200
    log = client.get("/api/tools/refunds/integrations", headers=h("dan")).json()
    assert log[0]["payload"]["signature"] == "unsigned"

    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "test-only-secret")
    refund = client.get("/api/tools/refunds/records?view=approved", headers=h("dan")).json()[0]
    client.post("/api/tools/refunds/actions/pay", json={"record_id": refund["id"], "comment": "release"}, headers=h("dan"))
    log = client.get("/api/tools/refunds/integrations", headers=h("dan")).json()
    assert log[0]["payload"]["signature"].startswith("sha256=")
    committed = [p for p in (ROOT / "tools").glob("*.yaml")] + [ROOT / "server" / "seed.py"]
    assert not any("test-only-secret" in p.read_text() for p in committed)


def test_dashboard_tiles_compute(client):
    tiles = client.get("/api/tools/refunds/dashboard", headers=h("sofia")).json()
    by_title = {t["title"]: t for t in tiles}
    assert by_title["Refund value (30d)"]["value"] > 0
    assert len(by_title["Refund value by day"]["data"]) == 14
    assert round(sum(d["value"] for d in by_title["Refund value by reason (30d)"]["data"]), 2) == round(by_title["Refund value (30d)"]["value"], 2)


def test_create_validates_choices_and_required(client):
    r = client.post("/api/tools/refunds/records", json={"merchant": "X", "amount": 5}, headers=h("sofia"))
    assert r.status_code == 400 and "Refund is required" in r.json()["detail"]
    r = client.post("/api/tools/refunds/records", json={"refund_id": "RF-1", "merchant": "X", "amount": 5, "rail": "Cheque"}, headers=h("sofia"))
    assert r.status_code == 400 and "one of" in r.json()["detail"]
    r = client.post("/api/tools/refunds/records", json={"refund_id": "RF-1", "merchant": "X", "amount": "12.5"}, headers=h("sofia"))
    assert r.status_code == 201 and r.json()["status"] == "Awaiting approval" and r.json()["currency"] == "GBP"


def test_refund_decisions_are_approve_reject_or_request_info(client):
    tool = client.get("/api/tools/refunds", headers=h("sofia")).json()
    assert {a["id"] for a in tool["actions"]}.isdisjoint({"hold", "resume"})
    assert {a["decision"] for a in tool["actions"] if a["decision"]} == {"approve", "reject", "info"}
    row = next(r for r in client.get("/api/tools/refunds/records?view=awaiting", headers=h("sofia")).json() if r["amount"] < 1000)
    rid = row["id"]
    assert client.post("/api/tools/refunds/actions/request_info", json={"record_id": rid}, headers=h("sofia")).json()["status"] == "Awaiting approval"
    assert client.post("/api/tools/refunds/actions/reject", json={"record_id": rid}, headers=h("sofia")).status_code == 400  # comment required
    assert client.post("/api/tools/refunds/actions/reject", json={"record_id": rid, "comment": "no evidence"}, headers=h("sofia")).json()["status"] == "Rejected"


# ---- knowledge base + policy checks -------------------------------------------------------------
@pytest.mark.parametrize("spec", [t for t in TOOLS.values() if t.checks], ids=[t.id for t in TOOLS.values() if t.checks])
def test_every_check_cites_a_clause_in_the_knowledge_base(client, spec: ToolSpec):
    docs = client.get("/api/knowledge", headers=h("marcus")).json()
    codes = set()
    for d in docs:
        codes |= {c["code"] for c in client.get(f"/api/knowledge/{d['id']}", headers=h("marcus")).json()["clauses"]}
    assert {c.clause for c in spec.checks} <= codes
    assert spec.auto_review and spec.auto_review.policy in {d["id"] for d in docs}


def test_policy_verdict_is_computed_not_stored(client):
    rows = client.get("/api/tools/kyc/records?view=open", headers=h("priya")).json()
    assert {r["policy_verdict"] for r in rows} <= {"Cleared", "Needs review", "Flagged"}
    assert all(r["policy_verdict"] == "Flagged" for r in rows if r["sanctions_hit"])
    assert "policy_verdict" not in client.get("/api/tools/kyc/records.csv?view=open", headers=h("marcus")).text.splitlines()[0]
    r = client.patch(f"/api/tools/kyc/records/{rows[0]['id']}", json={"policy_verdict": "Cleared"}, headers=h("marcus"))
    assert r.status_code == 200 and r.json()["policy_verdict"] == rows[0]["policy_verdict"]  # silently ignored


def test_record_review_explains_each_check_with_clause_text(client):
    row = next(r for r in client.get("/api/tools/kyc/records?view=open", headers=h("priya")).json() if r["sanctions_hit"])
    review = client.get(f"/api/tools/kyc/records/{row['id']}/review", headers=h("priya")).json()
    assert review["verdict"] == "Flagged" and review["policy"] == "kyc_review_policy"
    sanctions = next(c for c in review["checks"] if c["clause"] == "KYC-2.1")
    assert sanctions["passed"] is False and sanctions["outcome"] == "flag"
    assert "enhanced due diligence" in sanctions["clause_text"]


def test_auto_review_clears_flags_and_leaves_the_rest_for_humans(client):
    before = {r["id"]: r for r in client.get("/api/tools/kyc/records?view=open", headers=h("marcus")).json()
              if r["status"] in ("Pending", "In review")}
    assert client.post("/api/tools/kyc/auto-review", headers=h("auditor")).status_code == 403
    summary = client.post("/api/tools/kyc/auto-review", headers=h("marcus")).json()
    assert {"cleared", "flagged", "review", "items", "policy", "actor"} <= set(summary)
    assert summary["policy"] == "kyc_review_policy" and summary["actor"] == "devin-ai"
    assert sorted(summary["cleared"] + summary["flagged"] + summary["review"]) == sorted(r["case_id"] for r in before.values())
    items = {i["record_id"]: i for i in summary["items"]}
    for rid, r in before.items():
        after = client.get(f"/api/tools/kyc/records/{rid}", headers=h("marcus")).json()
        trail = client.get(f"/api/tools/kyc/audit?record_id={rid}", headers=h("marcus")).json()
        item = items[rid]
        # every decision is evidenced: each check cites a KB clause with its text and the values judged
        assert all(c["clause_text"] and c["clause_title"] and c["evidence"] for c in item["checks"])
        assert trail[0]["user_id"] == "devin-ai"
        if r["policy_verdict"] == "Cleared":
            assert after["status"] == "Approved" and item["outcome"] == "cleared" and item["action"] == "auto_approve"
            assert "KYC-2.1" in trail[0]["comment"] and "KYC-4.2" in trail[0]["comment"] and "sanctions_hit=False" in trail[0]["comment"]
        elif r["policy_verdict"] == "Flagged":
            assert after["status"] == "Escalated" and after["risk"] == "High" and item["outcome"] == "escalated"
            assert "KYC-2.1" in trail[0]["comment"] and "FAILED" in trail[0]["comment"]
        else:
            assert after["status"] == r["status"] and item["outcome"] == "review" and item["action"] is None
            assert trail[0]["action"] == "auto-review:hold" and "FAILED" in trail[0]["comment"]
    assert client.post("/api/tools/kyc/auto-review", headers=h("marcus")).json()["cleared"] == []  # idempotent


def test_humans_can_reset_ai_decisions_one_or_all(client):
    decided = client.get("/api/tools/kyc/ai-decisions", headers=h("marcus")).json()["records"]
    assert decided, "auto-review above should have changed some records"
    rid = decided[0]
    review = client.get(f"/api/tools/kyc/records/{rid}/review", headers=h("marcus")).json()
    d = review["ai_decision"]
    assert d["actor"] == "devin-ai" and d["action"] in ("auto_approve", "auto_escalate") and d["before"]
    # readonly cannot reset; an analyst can, and the record goes back to its pre-AI values
    assert client.post("/api/tools/kyc/ai-reset", json={"record_id": rid}, headers=h("auditor")).status_code == 403
    res = client.post("/api/tools/kyc/ai-reset", json={"record_id": rid, "comment": "false positive"}, headers=h("priya"))
    assert res.status_code == 200
    after = client.get(f"/api/tools/kyc/records/{rid}", headers=h("marcus")).json()
    assert all(after[k] == v for k, v in d["before"].items())
    trail = client.get(f"/api/tools/kyc/audit?record_id={rid}", headers=h("marcus")).json()
    assert trail[0]["action"] == "ai-reset" and trail[0]["user_id"] == "priya"
    assert "auto_" in trail[0]["comment"] and "false positive" in trail[0]["comment"]
    # once reset there is nothing left to undo on that record; a second reset is rejected
    assert client.get(f"/api/tools/kyc/records/{rid}/review", headers=h("marcus")).json()["ai_decision"] is None
    assert client.post("/api/tools/kyc/ai-reset", json={"record_id": rid}, headers=h("priya")).status_code == 400
    # a human decision after the AI's is never undone by a bulk reset
    other = next(i for i in decided if i != rid
                 and client.get(f"/api/tools/kyc/records/{i}", headers=h("marcus")).json()["status"] == "Escalated")
    assert client.post("/api/tools/kyc/actions/reject", json={"record_id": other, "comment": "human call"},
                       headers=h("marcus")).status_code == 200
    rest = client.post("/api/tools/kyc/ai-reset", json={"comment": "rerun after policy change"}, headers=h("marcus")).json()
    assert set(rest["reset"]) == set(decided) - {rid, other}
    assert client.get(f"/api/tools/kyc/records/{other}", headers=h("marcus")).json()["status"] == "Rejected"
    assert client.get("/api/tools/kyc/ai-decisions", headers=h("marcus")).json()["records"] == []
    assert client.get("/api/tools/kyc/audit", headers=h("marcus")).json()[0]["action"] == "ai-reset:all"


def test_refund_auto_review_only_approves_small_eligible_refunds(client):
    summary = client.post("/api/tools/refunds/auto-review", headers=h("sofia")).json()
    for r in client.get("/api/tools/refunds/records?view=approved", headers=h("dan")).json():
        if r["refund_id"] in summary["cleared"]:
            assert r["amount"] < 250 and r["risk"] != "High" and r["reviewer"] == "Devin AI"
    assert all(r["status"] == "Awaiting approval"
               for r in client.get("/api/tools/refunds/records?view=awaiting", headers=h("dan")).json())
    assert client.get("/api/tools/refunds/audit", headers=h("dan")).json()[0]["user_id"] == "devin-ai" or not summary["cleared"]


def test_group_tile_sums_value_field_not_group_key(client):
    tiles = client.get("/api/tools/refunds/dashboard", headers=h("dan")).json()
    by_reason = next(t for t in tiles if t["field"] == "reason")
    assert by_reason["value_field"] == "amount"
    assert sum(d["value"] for d in by_reason["data"]) > 0


# ---- embedded AI: summaries + NL filters are governed like everything else -------------------
def test_ai_summary_cites_policy_clauses_and_never_sends_protected_fields(client):
    from server import ai as ai_mod
    kyc = TOOLS["kyc"]
    priya = next(u for u in DIRECTORY.users if u.id == "priya")
    rows = client.get("/api/tools/kyc/records?view=open", headers=h("priya")).json()
    sent = {}
    orig = ai_mod.RulesProvider.summarize

    def spy(self, ctx):
        sent.update(ctx["record"])
        return orig(self, ctx)

    ai_mod.RulesProvider.summarize = spy
    try:
        s = client.post("/api/tools/kyc/ai/summary", json={"record_id": rows[0]["id"]}, headers=h("priya")).json()
    finally:
        ai_mod.RulesProvider.summarize = orig
    protected = {f.name for f in kyc.fields if f.visible_to is not None}
    assert protected and not (protected & set(sent)), "PII columns must never reach the model"
    assert s["source"] == "rules" and s["headline"] and s["recommendation"]
    assert any(c.clause in " ".join(s["bullets"]) for c in kyc.checks)
    assert priya.roles == ["analyst"]


def test_ai_query_compiles_to_governed_filter_and_is_audited(client):
    r = client.post("/api/tools/kyc/ai/query", json={"question": "high risk cases missing proof of address", "view": "open"},
                    headers=h("priya"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filter"] == {"risk": "High", "address_verified": False}
    assert body["rows"] and all(row["risk"] == "High" and not row["address_verified"] for row in body["rows"])
    assert all(row["status"] not in ("Approved", "Rejected") for row in body["rows"]), "view filter still applies"
    log = client.get("/api/tools/kyc/audit", headers=h("marcus")).json()
    assert any(a["action"] == "ai:query" and a["user_id"] == "priya" for a in log)


def test_ai_query_refunds_amount_and_relative_time(client):
    body = client.post("/api/tools/refunds/ai/query",
                       json={"question": "refunds over 500 in the last 7 days, largest first", "view": "all"},
                       headers=h("sofia")).json()
    assert body["filter"]["amount"] == {"gt": 500.0} and body["filter"]["requested_at"]["gte"] == "now-7d"
    assert body["sort"] == "amount desc"
    amounts = [r["amount"] for r in body["rows"]]
    assert amounts == sorted(amounts, reverse=True) and all(a > 500 for a in amounts)


def test_ai_query_cannot_filter_on_columns_the_user_cannot_see(client):
    from server.ai import AIService
    refunds = TOOLS["refunds"]
    sofia = next(u for u in DIRECTORY.users if u.id == "sofia")
    hidden = next(f.name for f in refunds.fields if f.visible_to and not set(f.visible_to) & set(sofia.roles))
    visible = [f.name for f in refunds.stored_fields if f.visible_to is None]
    clean = AIService._validate(refunds, {hidden: {"contains": "12"}, "amount": {"gt": 5}, "reason": "Bogus"}, visible)
    assert clean == {"amount": {"gt": 5}}


def test_ai_query_rejects_nonsense(client):
    r = client.post("/api/tools/kyc/ai/query", json={"question": "banana", "view": "open"}, headers=h("priya"))
    assert r.status_code == 400


def test_ai_endpoints_respect_tool_read_permission(client):
    r = client.post("/api/tools/kyc/ai/query", json={"question": "high risk"}, headers=h("lin"))
    assert r.status_code == 403


# ---- knowledge base index -----------------------------------------------------------------
def test_kb_indexes_every_clause_and_reuses_cached_vectors(client):
    st = client.get("/api/knowledge/status", headers=h("priya")).json()
    docs = client.get("/api/knowledge", headers=h("priya")).json()
    intros = sum(1 for d in docs if d["summary"])
    assert st["backend"] == "lexical" and st["chunks"] == sum(d["clauses"] for d in docs) + intros
    again = client.post("/api/knowledge/reindex", headers=h("priya")).json()
    assert again["embedded"] == 0 and again["reused"] == st["chunks"]  # nothing changed -> nothing re-embedded


def test_kb_search_finds_the_right_clause(client):
    hits = client.get("/api/knowledge/search", params={"q": "proof of address utility bill"}, headers=h("priya")).json()["hits"]
    assert hits[0]["chunk"]["clause"] == "KYC-3.2"
    hits = client.get("/api/knowledge/search", params={"q": "chargeback dispute window refund", "doc": "refund_policy"},
                      headers=h("sofia")).json()["hits"]
    assert hits and all(x["chunk"]["doc"] == "refund_policy" for x in hits)


def test_kb_search_requires_auth(client):
    assert client.get("/api/knowledge/search", params={"q": "x"}).status_code == 401


def test_ai_summary_sources_come_from_the_kb(client):
    rows = client.get("/api/tools/kyc/records", params={"view": "open"}, headers=h("priya")).json()
    s = client.post("/api/tools/kyc/ai/summary", json={"record_id": rows[0]["id"]}, headers=h("priya")).json()
    whys = {x["why"] for x in s["sources"]}
    assert "cited by check" in whys and "retrieved" in whys
    assert all(x["doc"] == "kyc_review_policy" for x in s["sources"])  # retrieval scoped to the tool's policy
    assert all(x["score"] is not None for x in s["sources"] if x["why"] == "retrieved")


def test_ai_ask_answers_from_retrieved_clauses_and_is_audited(client):
    rows = client.get("/api/tools/kyc/records", params={"view": "open"}, headers=h("marcus")).json()
    rid = rows[0]["id"]
    a = client.post("/api/tools/kyc/ai/ask", json={"question": "can an analyst approve this case?", "record_id": rid},
                    headers=h("marcus")).json()
    codes = [x["clause"] for x in a["sources"]]
    assert "KYC-1.2" in codes and a["source"] == "rules" and a["answer"]
    assert set(a["cites"]) <= set(codes)
    audit = client.get("/api/tools/kyc/audit", params={"record_id": rid}, headers=h("marcus")).json()
    assert audit[0]["action"] == "ai:ask" and "KYC-1.2" in audit[0]["after"]["retrieved"]


def test_flag_policy_checks_cite_the_feature_flag_kb(client):
    rows = client.get("/api/tools/flags/records", params={"view": "prod_no_cr"}, headers=h("lin")).json()
    assert rows and all(r["policy_verdict"] == "Flagged" for r in rows)
    review = client.get(f"/api/tools/flags/records/{rows[0]['id']}/review", headers=h("lin")).json()
    failed = {c["clause"] for c in review["checks"] if not c["passed"]}
    assert "FF-2.1" in failed
    unowned = [r for r in client.get("/api/tools/flags/records", headers=h("lin")).json() if not r["owner"]]
    review = client.get(f"/api/tools/flags/records/{unowned[0]['id']}/review", headers=h("lin")).json()
    assert "FF-1.2" in {c["clause"] for c in review["checks"] if not c["passed"]}
    hits = client.get("/api/knowledge/search", params={"q": "who may approve a change request", "doc": "feature_flag_policy"},
                      headers=h("lin")).json()["hits"]
    assert hits[0]["chunk"]["clause"] in ("FF-2.2", "FF-2.1")


def test_ai_ask_respects_tool_read_permission(client):
    r = client.post("/api/tools/refunds/ai/ask", json={"question": "what is the refund window?"}, headers=h("priya"))
    assert r.status_code == 403


def test_concurrent_requests_share_one_sqlite_connection_safely(client):
    """Opening a record fires several API calls at once; they must not trip sqlite's
    single-connection threading limits (InterfaceError: bad parameter or other API misuse)."""
    rows = client.get("/api/tools/refunds/records", headers=h("sofia")).json()[:5]
    calls = []
    for r in rows:
        calls += [
            lambda rid=r["id"]: client.get(f"/api/tools/refunds/records/{rid}", headers=h("sofia")),
            lambda rid=r["id"]: client.get(f"/api/tools/refunds/records/{rid}/review", headers=h("sofia")),
            lambda rid=r["id"]: client.post("/api/tools/refunds/ai/summary", json={"record_id": rid}, headers=h("sofia")),
            lambda: client.get("/api/tools/refunds/dashboard", headers=h("sofia")),
        ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda f: f(), calls * 3))
    assert all(r.status_code == 200 for r in results), [r.status_code for r in results if r.status_code != 200]


# ---- one image per tool: TOOLS=<id> restricts what a process loads, seeds and serves ---------
def test_load_tools_only_filters_and_rejects_unknown_ids():
    assert list(load_tools(TOOLS_DIR, only="kyc")) == ["kyc"]
    assert set(load_tools(TOOLS_DIR, only="kyc, flags")) == {"kyc", "flags"}
    with pytest.raises(ValueError, match="no_such_tool"):
        load_tools(TOOLS_DIR, only="no_such_tool")


def test_single_tool_instance_seeds_and_serves_only_that_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TOOLS", "refunds")
    db = tmp_path / "refunds.db"
    seed(db, TOOLS_DIR)
    c = TestClient(build_app(TOOLS_DIR, db, provider=RulesProvider(), embedder=LexicalEmbedder()))
    assert {u["id"] for u in c.get("/api/users").json()} == {"sofia", "dan", "auditor"}  # only personas with a board here
    assert [t["id"] for t in c.get("/api/me", headers=h("sofia")).json()["tools"]] == ["refunds"]
    assert c.get("/api/tools/refunds/records?view=awaiting&q=", headers=h("sofia")).status_code == 200
    assert c.get("/api/tools/kyc", headers=h("marcus")).status_code == 404
    assert len(c.get("/api/tools/refunds/records?view=all&q=", headers=h("sofia")).json()) == 160


def test_seed_data_is_identical_whether_or_not_other_tools_ship(tmp_path: Path, monkeypatch):
    seed(tmp_path / "all.db", TOOLS_DIR)
    monkeypatch.setenv("TOOLS", "kyc")
    seed(tmp_path / "kyc.db", TOOLS_DIR)
    rows = lambda p: sqlite3.connect(p).execute("SELECT applicant, risk_score, status FROM kyc_case ORDER BY id").fetchall()  # noqa: E731
    assert rows(tmp_path / "all.db") == rows(tmp_path / "kyc.db")
