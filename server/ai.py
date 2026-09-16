"""AI features embedded in the tools: case summaries and natural-language filters.

Two providers behind one interface:
  * OpenAIProvider  - real LLM, used when OPENAI_API_KEY is set (Devin secrets store -> env var, never committed)
  * RulesProvider   - deterministic fallback so the demo, tests and CI work offline

Data minimisation: records are redacted with the *requesting user's* column-level security before anything is
sent to a model, and fields marked visible_to (PII: document numbers, DOB, bank accounts) are never sent at all.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from .engine import Engine, Invalid
from .knowledge import Clause
from .spec import Filter, ToolSpec, User

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class Summary(BaseModel):
    headline: str
    bullets: list[str]
    recommendation: str
    source: str


class Query(BaseModel):
    filter: Filter
    sort: str | None = None
    explanation: str
    source: str


class Provider(Protocol):
    name: str
    last_error: str | None

    def summarize(self, context: dict) -> Summary: ...

    def query(self, question: str, schema: dict) -> Query: ...


# ---- redaction ------------------------------------------------------------------------------
def redact(spec: ToolSpec, record: dict) -> dict:
    """Drop every protected column outright - masked placeholders are not sent either."""
    return {f.name: record.get(f.name) for f in spec.fields if f.visible_to is None and f.name in record}


def schema_for_prompt(spec: ToolSpec, user_visible: list[str]) -> dict:
    return {
        "entity": spec.entity,
        "fields": [
            {"name": f.name, "label": f.label, "type": f.type, **({"options": f.options} if f.options else {})}
            for f in spec.stored_fields if f.name in user_visible
        ],
        "operators": ["eq", "ne", "lt", "lte", "gt", "gte", "contains", "list of values"],
        "relative_time": "strings like now-7d / now+4h are allowed for date fields",
    }


# ---- rules provider (offline) ---------------------------------------------------------------
_NUM = r"(\d+(?:\.\d+)?)"


class RulesProvider:
    name = "rules"
    last_error = None

    def summarize(self, ctx: dict) -> Summary:
        rec, review, audit, spec = ctx["record"], ctx["review"], ctx["audit"], ctx["spec"]
        failed = [c for c in review["checks"] if not c["passed"]]
        passed = [c for c in review["checks"] if c["passed"]]
        title = rec.get(spec["title_field"], "record")
        bullets = []
        for c in failed:
            bullets.append(f"{c['clause']} {c['title']}: {c['detail']}")
        if passed:
            bullets.append(f"Cleared {len(passed)} of {len(review['checks'])} policy checks "
                           f"({', '.join(c['clause'] for c in passed)}).")
        if audit:
            last = audit[0]
            bullets.append(f"Last activity: {last['action'].replace('action:', '')} by {last['user_id']} "
                           f"({len(audit)} audit entries).")
        if not bullets:
            bullets.append("No policy checks configured for this tool.")
        verdict = review["verdict"]
        rec_text = {
            "Cleared": "Eligible for straight-through processing; no reviewer action needed beyond confirmation.",
            "Flagged": "Do not approve. Route to escalation - a mandatory policy control failed.",
            "Needs review": "Reviewer decision required on the failed checks above; everything else is settled.",
        }.get(verdict, "Review manually.")
        return Summary(headline=f"{title}: {verdict.lower()} by automated policy checks", bullets=bullets,
                       recommendation=rec_text, source=self.name)

    def query(self, question: str, schema: dict) -> Query:
        q = question.lower()
        fields = {f["name"]: f for f in schema["fields"]}
        flt: Filter = {}
        sort: str | None = None
        notes: list[str] = []

        def has(name: str) -> bool:
            return name in fields

        # numeric comparisons: "amount > 500", "score above 70", "over 1000", "under 250"
        for m in re.finditer(rf"(\w[\w ]*?)\s*(>=|<=|>|<|above|over|more than|greater than|below|under|less than)\s*[£$€]?{_NUM}", q):
            phrase, op, num = m.group(1).strip(), m.group(2), float(m.group(3))
            target = next((n for n in fields if fields[n]["type"] in ("number", "money", "percent")
                           and (n in phrase or fields[n]["label"].lower() in phrase or phrase.endswith(n.split("_")[-1]))), None)
            if target is None:
                target = next((n for n in fields if fields[n]["type"] in ("money", "number")), None)
            if target:
                key = "gte" if op in (">=",) else "lte" if op in ("<=",) else \
                    "gt" if op in (">", "above", "over", "more than", "greater than") else "lt"
                flt.setdefault(target, {})[key] = num
                notes.append(f"{fields[target]['label']} {key} {num:g}")
        # relative dates
        date_field = next((n for n in fields if fields[n]["type"] == "datetime"), None)
        m = re.search(r"last (\d+) days?|last week|past week|today|yesterday|last (\d+) hours?", q)
        if m and date_field:
            if "week" in m.group(0):
                days = 7
            elif "today" in m.group(0):
                days = 1
            elif "yesterday" in m.group(0):
                days = 2
            elif m.group(2):
                days = 0
                flt[date_field] = {"gte": f"now-{m.group(2)}h"}
                notes.append(f"{fields[date_field]['label']} in the last {m.group(2)}h")
            else:
                days = int(m.group(1))
            if days:
                flt[date_field] = {"gte": f"now-{days}d"}
                notes.append(f"{fields[date_field]['label']} in the last {days} days")
        if "overdue" in q and has("sla_due"):
            flt["sla_due"] = {"lt": "now"}
            notes.append("SLA already breached")
        # choice values mentioned verbatim ("high risk", "pending", "fraud reversal")
        for n, f in fields.items():
            hits = [o for o in f.get("options", []) if re.search(rf"\b{re.escape(o.lower())}\b", q)]
            if hits and n != "policy_verdict":
                if n == "risk" and not re.search(r"\b(low|medium|high)( |-)?risk\b", q):
                    continue
                flt[n] = hits if len(hits) > 1 else hits[0]
                notes.append(f"{f['label']} = {', '.join(hits)}")
        # domain phrases
        if re.search(r"missing|incomplete|without", q) and re.search(r"proof|address|document|docs", q):
            if "address" in q and has("address_verified"):
                flt["address_verified"] = False
                notes.append("address not verified")
            if re.search(r"document|docs", q) and has("docs_complete"):
                flt["docs_complete"] = {"lt": 100}
                notes.append("documents incomplete")
        if re.search(r"sanction|pep", q) and has("sanctions_hit"):
            flt["sanctions_hit"] = True
            notes.append("sanctions/PEP hit")
        if re.search(r"flagged|failed (policy|checks)", q) and has("policy_verdict"):
            pass  # computed field, filtered client-side by the caller
        if re.search(r"repeat|velocity|multiple refunds", q) and has("prior_refunds_90d"):
            flt["prior_refunds_90d"] = {"gte": 2}
            notes.append("2+ prior refunds in 90 days")
        if re.search(r"unassigned|no assignee|nobody", q) and has("assignee"):
            flt["assignee"] = ""
            notes.append("unassigned")
        m = re.search(r"(sort|order)(ed)? by (\w+)( desc| asc)?", q)
        if m:
            cand = next((n for n in fields if m.group(3) in n or m.group(3) in fields[n]["label"].lower()), None)
            if cand:
                sort = f"{cand} {'asc' if (m.group(4) or '').strip() == 'asc' else 'desc'}"
        elif "largest" in q or "biggest" in q:
            money = next((n for n in fields if fields[n]["type"] == "money"), None)
            if money:
                sort = f"{money} desc"
        if not flt and not sort:
            raise Invalid("Couldn't turn that into a filter. Try e.g. 'high risk cases missing proof of address' "
                          "or 'refunds over 500 in the last 7 days'.")
        return Query(filter=flt, sort=sort, explanation="; ".join(notes) or "sorted", source=self.name)


# ---- OpenAI provider ------------------------------------------------------------------------
class OpenAIProvider:
    name = "openai"

    COOLDOWN_S = 300  # after an auth/quota failure, use the fallback without retrying for a while

    def __init__(self, api_key: str, fallback: RulesProvider):
        self.key = api_key
        self.fallback = fallback
        self.last_error: str | None = None
        self._paused_until = 0.0

    def _chat(self, system: str, user: str) -> dict:
        if time.monotonic() < self._paused_until:
            raise httpx.HTTPError(self.last_error or "provider paused")
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": OPENAI_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=30,
        )
        if r.status_code >= 400:
            try:
                detail = r.json()["error"]["code"] or r.json()["error"]["message"]
            except (ValueError, KeyError):
                detail = r.text[:120]
            raise httpx.HTTPStatusError(f"{r.status_code} {detail}", request=r.request, response=r)
        self.last_error = None
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _fail(self, e: Exception) -> None:
        self.last_error = str(e)[:160]
        if isinstance(e, httpx.HTTPStatusError) and (
            e.response.status_code in (401, 403) or "insufficient_quota" in str(e)
        ):
            self._paused_until = time.monotonic() + self.COOLDOWN_S

    def summarize(self, ctx: dict) -> Summary:
        system = (
            "You are a compliance operations assistant inside an internal fintech tool. Summarise the record for a "
            "human reviewer in plain English. Be specific, cite policy clause codes (e.g. KYC-2.1) when you refer to "
            "a check, never invent facts not present in the input, and never speculate about identity documents "
            "or bank details (they have been removed). Return JSON: {\"headline\": str (<=90 chars), "
            "\"bullets\": [str, ...] (3-5 items), \"recommendation\": str (one sentence, what the reviewer should do)}"
        )
        payload = {k: ctx[k] for k in ("record", "review", "audit", "policy_excerpts")}
        try:
            out = self._chat(system, json.dumps(payload, default=str))
            return Summary(headline=str(out["headline"]), bullets=[str(b) for b in out["bullets"]][:5],
                           recommendation=str(out["recommendation"]), source=self.name)
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as e:
            self._fail(e)
            return self.fallback.summarize(ctx)

    def query(self, question: str, schema: dict) -> Query:
        system = (
            "Translate the user's question about a table into a filter object. Only use the field names given. "
            "Filter grammar: {field: value} equality, {field: [v1, v2]} membership, "
            "{field: {op: value}} with op in lt|lte|gt|gte|ne|eq|contains. Booleans are true/false. "
            "For date fields use relative strings like 'now-7d' or 'now+4h'. "
            "Return JSON: {\"filter\": {...}, \"sort\": \"field asc|desc\" or null, \"explanation\": str}. "
            "If the question cannot be answered with these fields return {\"filter\": {}, \"sort\": null, "
            "\"explanation\": \"cannot\"}."
        )
        try:
            out = self._chat(system, json.dumps({"question": question, "schema": schema}))
            q = Query(filter=out.get("filter") or {}, sort=out.get("sort"), explanation=str(out.get("explanation", "")),
                      source=self.name)
            if not q.filter and not q.sort:
                raise Invalid(f"The model could not map that question onto {schema['entity']} fields.")
            return q
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as e:
            self._fail(e)
            return self.fallback.query(question, schema)


def make_provider() -> Provider:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    rules = RulesProvider()
    return OpenAIProvider(key, rules) if key else rules


# ---- service --------------------------------------------------------------------------------
class AIService:
    def __init__(self, engine: Engine, provider: Provider, clause_lookup: Callable[[str], Clause | None]):
        self.engine = engine
        self.provider = provider
        self.clause = clause_lookup

    def summarize(self, spec: ToolSpec, user: User, rid: int) -> Summary:
        raw = self.engine.get_record(spec, user, rid, raw=True)
        review = self.engine.review(spec, raw)
        audit = self.engine.audit(spec, user, rid)[:8]
        excerpts = []
        for c in review["checks"]:
            cl = self.clause(c["clause"])
            if cl:
                excerpts.append({"clause": cl.code, "title": cl.title, "text": cl.text})
        ctx = {
            "spec": {"title_field": spec.title_field, "entity": spec.entity},
            "record": redact(spec, raw),
            "review": review,
            "audit": [{"ts": a["ts"], "user_id": a["user_id"], "action": a["action"], "comment": a["comment"]} for a in audit],
            "policy_excerpts": excerpts,
        }
        return self.provider.summarize(ctx)

    def query(self, spec: ToolSpec, user: User, question: str, view_id: str | None) -> dict:
        self.engine.require(spec, user, "read")
        visible = [f.name for f in spec.stored_fields if f.visible_to is None or self.engine._has_role(user, f.visible_to)]
        schema = schema_for_prompt(spec, visible)
        q = self.provider.query(question.strip(), schema)
        clean = self._validate(spec, q.filter, visible)
        rows = self.engine.list_records(spec, user, view_id, extra=clean)
        if q.sort:
            fld, _, d = q.sort.partition(" ")
            if fld in visible:
                rows.sort(key=lambda r: (r.get(fld) is None, r.get(fld)), reverse=d.lower() != "asc")
        self.engine._audit(spec, None, user, "ai:query", question.strip()[:200], None, {"filter": clean, "source": q.source})
        self.engine.conn.commit()
        return {"filter": clean, "sort": q.sort, "explanation": q.explanation, "source": q.source, "rows": rows}

    @staticmethod
    def _validate(spec: ToolSpec, flt: Filter, visible: list[str]) -> Filter:
        """The model's output is untrusted: only visible, stored fields and known operators survive."""
        clean: Filter = {}
        ops = {"lt", "lte", "gt", "gte", "ne", "eq", "contains"}
        for field, cond in flt.items():
            if field not in visible:
                continue
            f = spec.field(field)
            if isinstance(cond, dict):
                good = {op: v for op, v in cond.items() if op in ops and isinstance(v, (str, int, float, bool))}
                if good:
                    clean[field] = good
            elif isinstance(cond, list):
                vals = [v for v in cond if isinstance(v, (str, int, float, bool))]
                if f.options:
                    vals = [v for v in vals if v in f.options]
                if vals:
                    clean[field] = vals
            elif isinstance(cond, (str, int, float, bool)):
                if f.options and cond not in f.options:
                    continue
                clean[field] = cond
        return clean

