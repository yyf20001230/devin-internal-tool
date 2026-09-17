"""Demo data. `python -m server.seed` rebuilds data.db."""
from __future__ import annotations

import random
from datetime import timedelta
from pathlib import Path

from .engine import Engine, now
from .main import DB_PATH, TOOLS_DIR
from .spec import User, load_tools

SYSTEM = User(id="system", name="system", roles=["compliance_lead", "finance", "release_manager", "engineer", "payments_ops", "analyst"])


def iso(dt):
    return dt.isoformat(timespec="seconds")


def seed(db_path: Path | str = DB_PATH, tools_dir: Path = TOOLS_DIR) -> None:
    random.seed(7)
    Path(db_path).unlink(missing_ok=True)
    tools = load_tools(tools_dir)
    eng = Engine(db_path, tools)
    t = now()

    # ---- KYC ----------------------------------------------------------------------
    kyc = tools["kyc"]
    analysts = ["Priya Nair", "Marcus Chen", "Jonas Berg", "Aisha Khan"]
    countries = ["GB", "DE", "NG", "US", "FR", "AE", "IN", "BR"]
    applicants = ["Northwind Traders Ltd", "Aurora Fintech GmbH", "Lagos Freight Co", "Okonkwo Holdings",
                  "Meridian Payments Inc", "Blue Harbour Foods", "Zenith Logistics", "Sahara Textiles",
                  "Kite Software Ltd", "Petrov & Sons", "Maple Retail Group", "Coral Bay Resorts",
                  "Quantum Ventures", "Delta Farms Cooperative", "Ivory Coast Exports", "Harbour Capital",
                  "Oslo Marine AS", "Tandem Mobility", "Silverline Media", "Crescent Pharma",
                  "Birch Lane Bakery", "Atlas Courier Ltd", "Fjord Analytics", "Sunrise Dental Group",
                  "Lumen Studios", "Granite Build Co", "Willow Home Care", "Pioneer Robotics"]
    for i, name in enumerate(applicants):
        score = random.randint(8, 96)
        risk = "High" if score >= 70 else "Medium" if score >= 40 else "Low"
        decided = i >= 22
        status = random.choice(["Approved", "Rejected"]) if decided else random.choice(["Pending", "In review", "In review", "Escalated"])
        if status == "Escalated":
            risk = "High"
        opened = t - timedelta(days=random.randint(0, 13), hours=random.randint(0, 20))
        eng.create_record(kyc, SYSTEM, {
            "case_id": f"KYC-{10470 + i}", "applicant": name, "country": random.choice(countries),
            "risk": risk, "risk_score": score, "sanctions_hit": score > 80 or random.random() < 0.1,
            "docs_complete": random.choice([40, 60, 80, 100, 100, 100]),
            "address_verified": random.random() < 0.8,
            "id_document_number": f"P{random.randint(10000000, 99999999)}",
            "date_of_birth": f"19{random.randint(60, 99)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "status": status, "assignee": random.choice(analysts),
            "sla_due": iso(t + timedelta(hours=random.choice([-3, 1, 2, 3, 6, 12, 26, 40, 60]))), "opened_at": iso(opened),
            "notes": "Sanctions screening returned a partial name match; awaiting UBO declaration." if score > 80 else "",
        })

    # ---- Refunds -----------------------------------------------------------------------
    ref = tools["refunds"]
    merchants = ["Bloom & Co", "Northwind Traders", "Fitlab", "Cloudpress", "Urban Bikes", "Petrov Digital",
                 "Maple Retail", "Tandem Mobility", "Silverline Media", "Harbour Grill"]
    reasons = ref.field("reason").options
    for i in range(160):
        requested = t - timedelta(days=random.randint(0, 29), hours=random.randint(0, 23))
        amount = round(random.choice([random.uniform(5, 120), random.uniform(50, 600), random.uniform(800, 4200)]), 2)
        reason = random.choices(reasons, weights=[30, 22, 20, 8, 12, 8])[0]
        risk = "High" if reason == "Fraud reversal" or amount > 2500 else "Medium" if amount > 600 else "Low"
        if requested > t - timedelta(days=2) and i % 3:
            status = "Awaiting approval"
        else:
            status = random.choices(["Approved", "Paid", "Rejected"], weights=[30, 60, 10])[0]
        eng.create_record(ref, SYSTEM, {
            "refund_id": f"RF-{88210 + i}", "merchant": random.choice(merchants), "amount": amount,
            "currency": random.choices(["GBP", "EUR", "USD"], weights=[6, 3, 1])[0],
            "rail": random.choices(["Card", "Bank transfer", "Wallet"], weights=[6, 3, 1])[0],
            "reason": reason, "risk": risk,
            "days_since_purchase": random.choices([random.randint(1, 30), random.randint(31, 60), random.randint(61, 120)], weights=[6, 3, 1])[0],
            "prior_refunds_90d": random.choices([0, 1, 2, 3, 4], weights=[55, 25, 10, 7, 3])[0],
            "customer_email": f"customer{random.randint(100, 999)}@example.com",
            "bank_account": f"GB{random.randint(10, 99)}BARC{random.randint(10000000000000, 99999999999999)}",
            "status": status, "reviewer": random.choice(["Sofia Alvarez", "Dan Whitfield", ""]) if status != "Awaiting approval" else random.choice(["Sofia Alvarez", ""]),
            "requested_at": iso(requested),
        })

    # ---- Feature flags -----------------------------------------------------------------
    fl = tools["flags"]
    flags = [
        ("refunds.instant-card-refunds", "refunds-svc", "Instant card refunds via network push", True, True, True, 25, "CR-2231", "Approved", "Lin Zhao", False),
        ("payments.3ds2-challenge-flow", "payments-api", "Force 3DS2 challenge on high-risk", True, True, True, 100, "CR-2198", "Approved", "Amara Okafor", False),
        ("onboarding.selfie-liveness", "onboarding", "Liveness check during ID capture", True, True, False, 0, "CR-2240", "Pending", "Priya Nair", False),
        ("ledger.double-entry-v2", "ledger", "New ledger posting engine", True, False, False, 0, "", "None", "Lin Zhao", False),
        ("web.new-merchant-dashboard", "web-app", "Redesigned merchant dashboard", True, True, True, 10, "", "None", "", False),
        ("payments.apple-pay", "payments-api", "Apple Pay acceptance", True, True, True, 100, "CR-1902", "Approved", "Lin Zhao", True),
        ("refunds.auto-approve-under-50", "refunds-svc", "Skip manual review for refunds < 50", True, True, False, 0, "CR-2244", "Pending", "Sofia Alvarez", False),
        ("onboarding.sanctions-v3", "onboarding", "New sanctions screening provider", True, False, False, 0, "", "None", "Marcus Chen", False),
        ("web.dark-mode", "web-app", "Dark mode", True, True, True, 100, "CR-1811", "Approved", "Amara Okafor", True),
        ("payments.open-banking-payouts", "payments-api", "Payouts over open banking", True, True, True, 50, "CR-2250", "Rejected", "Lin Zhao", False),
    ]
    for key, svc, desc, dev, uat, prod, roll, cr, crs, owner, stale in flags:
        eng.create_record(fl, SYSTEM, {
            "key": key, "service": svc, "description": desc, "dev": dev, "uat": uat, "prod": prod,
            "rollout": roll, "change_request": cr, "cr_status": crs, "owner": owner,
            "last_changed": iso(t - timedelta(days=random.randint(0, 60))), "stale": stale,
        })

    # ---- Chargebacks (4th tool demo) ----------------------------------------------------
    cb = tools["chargebacks"]
    codes = cb.field("reason_code").options
    for i in range(36):
        closed = i >= 22
        status = random.choices(["Won", "Lost", "Accepted loss"], weights=[5, 3, 2])[0] if closed else "Open"
        evidence = random.choice(["Not started", "Gathering", "Submitted"]) if not closed else ("Not contesting" if status == "Accepted loss" else "Submitted")
        eng.create_record(cb, SYSTEM, {
            "dispute_id": f"CB-{50210 + i}", "merchant": random.choice(merchants),
            "amount": round(random.uniform(20, 1800), 2), "currency": random.choices(["GBP", "EUR", "USD"], weights=[6, 3, 1])[0],
            "reason_code": random.choices(codes, weights=[35, 25, 15, 15, 10])[0],
            "deadline": iso(t + timedelta(hours=random.choice([6, 20, 30, 44, 70, 120, 200, 300]))),
            "evidence_status": evidence, "status": status,
            "handler": random.choice(["Sofia Alvarez", "Dan Whitfield", "Ravi Patel"]),
            "cardholder_name": random.choice(["A. Thompson", "M. Dubois", "K. Okafor", "L. Chen", "S. Novak"]),
            "card_last4": f"{random.randint(1000, 9999)}",
        })

    # wipe the noisy seed audit rows so the audit pane shows real user activity
    eng.conn.execute("DELETE FROM audit_log")
    eng.conn.commit()
    print(f"seeded {db_path}: " + ", ".join(f"{k}={eng.count(v)}" for k, v in tools.items()))


if __name__ == "__main__":
    seed()
