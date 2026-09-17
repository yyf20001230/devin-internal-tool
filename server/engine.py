"""Generic data engine: turns a ToolSpec into SQLite tables and governed operations."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .spec import VERDICT_FIELD, Filter, ToolSpec, User, filter_fields

SQL_TYPES = {
    "text": "TEXT", "multiline": "TEXT", "choice": "TEXT", "date": "TEXT", "datetime": "TEXT",
    "number": "REAL", "money": "REAL", "percent": "REAL", "boolean": "INTEGER",
}
MASK = "••••••"


class Forbidden(Exception):
    pass


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def _cite(check: dict) -> str:
    """One-line citation for an audit comment: clause, verdict and the values it was judged on."""
    values = ", ".join(f"{k}={v}" for k, v in check["evidence"].items())
    return f"{check['clause']} {check['title']} {'passed' if check['passed'] else 'FAILED'} ({values})"


def sign_payload(payload: dict) -> str:
    """HMAC for outbound webhooks. The secret comes from the environment (Devin secrets store /
    deployment secret manager) and is never read from YAML or committed files."""
    secret = os.environ.get("WEBHOOK_SIGNING_SECRET", "")
    if not secret:
        return "unsigned"
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _resolve_time(value: object) -> object:
    """Allow relative times like 'now', 'now+4h', 'now-30d' in filters."""
    if isinstance(value, str) and value.startswith("now"):
        m = re.fullmatch(r"now([+-]\d+)([hdm])", value)
        delta = timedelta()
        if m:
            n = int(m.group(1))
            delta = {"h": timedelta(hours=n), "d": timedelta(days=n), "m": timedelta(minutes=n)}[m.group(2)]
        return (now() + delta).isoformat(timespec="seconds")
    return value


def compile_filter(flt: Filter, params: list) -> str:
    """Filter -> SQL WHERE fragment. {f: v}, {f: [v..]}, {f: {lt|lte|gt|gte|ne|contains: v}}, {any: [filter..]}"""
    clauses = []
    for field, cond in flt.items():
        if field == "any" and isinstance(cond, list):
            clauses.append("(" + " OR ".join(f"({compile_filter(sub, params)})" for sub in cond) + ")")
            continue
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", field):
            raise Invalid(f"bad field name {field!r}")
        if isinstance(cond, list):
            clauses.append(f"{field} IN ({','.join('?' * len(cond))})")
            params.extend(cond)
        elif isinstance(cond, dict):
            for op, v in cond.items():
                sql_op = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=", "ne": "!=", "eq": "="}.get(op)
                if op == "contains":
                    clauses.append(f"{field} LIKE ?")
                    params.append(f"%{v}%")
                elif sql_op:
                    clauses.append(f"{field} {sql_op} ?")
                    params.append(_resolve_time(v))
                else:
                    raise Invalid(f"unknown operator {op!r}")
        else:
            clauses.append(f"{field} = ?")
            params.append(int(cond) if isinstance(cond, bool) else cond)
    return " AND ".join(clauses) or "1=1"


def matches(flt: Filter, record: dict) -> bool:
    """In-memory equivalent of compile_filter, used for action guards."""
    for field, cond in flt.items():
        if field == "any" and isinstance(cond, list):
            if not any(matches(sub, record) for sub in cond):
                return False
            continue
        v = record.get(field)
        if isinstance(cond, list):
            if v not in cond:
                return False
        elif isinstance(cond, dict):
            for op, x in cond.items():
                x = _resolve_time(x)
                ok = {
                    "lt": lambda: v is not None and v < x, "lte": lambda: v is not None and v <= x,
                    "gt": lambda: v is not None and v > x, "gte": lambda: v is not None and v >= x,
                    "ne": lambda: v is not None and v != x, "eq": lambda: v == x,  # NULL != x is unknown, as in SQL
                    "contains": lambda: isinstance(v, str) and str(x) in v,
                }[op]()
                if not ok:
                    return False
        else:
            if isinstance(cond, bool):
                cond = int(cond)
            if v != cond:
                return False
    return True


class Engine:
    def __init__(self, db_path: Path | str, tools: dict[str, ToolSpec]):
        self.tools = tools
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                 id INTEGER PRIMARY KEY, ts TEXT, tool TEXT, record_id INTEGER, user_id TEXT,
                 action TEXT, comment TEXT, before TEXT, after TEXT)"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS integration_log (
                 id INTEGER PRIMARY KEY, ts TEXT, tool TEXT, record_id INTEGER, webhook TEXT, payload TEXT)"""
        )
        for spec in tools.values():
            self._ensure_table(spec)
        self.conn.commit()

    # ---- schema --------------------------------------------------------------------
    def _ensure_table(self, spec: ToolSpec) -> None:
        cols = ", ".join(f"{f.name} {SQL_TYPES[f.type]}" for f in spec.stored_fields)
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {spec.entity} (id INTEGER PRIMARY KEY, created_at TEXT, updated_at TEXT, {cols})"
        )
        existing = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({spec.entity})")}
        for f in spec.stored_fields:  # additive migrations: new YAML field -> new column
            if f.name not in existing:
                self.conn.execute(f"ALTER TABLE {spec.entity} ADD COLUMN {f.name} {SQL_TYPES[f.type]}")

    # ---- permissions ------------------------------------------------------------------
    @staticmethod
    def _has_role(user: User, roles: list[str]) -> bool:
        return bool(set(user.roles) & set(roles))

    def require(self, spec: ToolSpec, user: User, op: str) -> None:
        if not self._has_role(user, getattr(spec.permissions, op)):
            raise Forbidden(f"{user.name} may not {op} {spec.name}")

    def visible_tools(self, user: User) -> list[ToolSpec]:
        return [t for t in self.tools.values() if self._has_role(user, t.permissions.read)]

    def _mask(self, spec: ToolSpec, user: User, row: dict) -> dict:
        out = dict(row)
        if spec.checks and "id" in row:
            out[VERDICT_FIELD] = self.review(spec, row)["verdict"]
        for f in spec.fields:
            if f.visible_to is not None and not self._has_role(user, f.visible_to):
                v = out.get(f.name)
                if v is None:
                    continue
                out[f.name] = f"••••{str(v)[-4:]}" if f.mask == "last4" and len(str(v)) > 4 else MASK
        return out

    def _coerce(self, spec: ToolSpec, values: dict, user: User, partial: bool) -> dict:
        clean = {}
        for f in spec.stored_fields:
            if f.name not in values:
                if not partial and f.default is not None:
                    clean[f.name] = f.default
                elif not partial and f.required:
                    raise Invalid(f"{f.label} is required")
                continue
            if f.visible_to is not None and not self._has_role(user, f.visible_to):
                raise Forbidden(f"{user.name} may not write {f.label}")
            v = values[f.name]
            if v in ("", None):
                if f.required:
                    raise Invalid(f"{f.label} is required")
                clean[f.name] = None
                continue
            if f.type == "choice" and v not in f.options:
                raise Invalid(f"{f.label} must be one of {f.options}")
            if f.type in ("number", "money", "percent"):
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    raise Invalid(f"{f.label} must be a number")
            if f.type == "boolean":
                v = 1 if v in (True, 1, "true", "1", "yes") else 0
            clean[f.name] = v
        return clean

    # ---- records ---------------------------------------------------------------------
    def list_records(self, spec: ToolSpec, user: User, view_id: str | None = None, q: str = "",
                     extra: Filter | None = None) -> list[dict]:
        self.require(spec, user, "read")
        params: list = []
        where = []
        order = "id DESC"
        if view_id:
            view = next((v for v in spec.views if v.id == view_id), None)
            if view is None:
                raise NotFound(f"view {view_id}")
            where.append(compile_filter(view.filter, params))
            if view.mine and spec.assignee_field:
                where.append(f"{spec.assignee_field} = ?")
                params.append(user.name)
            if view.sort:
                fld, _, d = view.sort.partition(" ")
                spec.field(fld)
                order = f"{fld} {'DESC' if d.lower() == 'desc' else 'ASC'}"
        if extra:
            where.append(compile_filter(extra, params))
        if q:
            text_cols = [f.name for f in spec.stored_fields if f.type in ("text", "multiline", "choice")
                         and (f.visible_to is None or self._has_role(user, f.visible_to))]
            where.append("(" + " OR ".join(f"{c} LIKE ?" for c in text_cols) + ")")
            params.extend([f"%{q}%"] * len(text_cols))
        sql = f"SELECT * FROM {spec.entity} WHERE {' AND '.join(where) or '1=1'} ORDER BY {order} LIMIT 500"
        return [self._mask(spec, user, dict(r)) for r in self.conn.execute(sql, params)]

    def _raw(self, spec: ToolSpec, rid: int) -> dict:
        row = self.conn.execute(f"SELECT * FROM {spec.entity} WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise NotFound(f"record {rid}")
        return dict(row)

    def get_record(self, spec: ToolSpec, user: User, rid: int, raw: bool = False) -> dict:
        self.require(spec, user, "read")
        row = self._raw(spec, rid)
        return row if raw else self._mask(spec, user, row)

    def create_record(self, spec: ToolSpec, user: User, values: dict) -> dict:
        self.require(spec, user, "create")
        clean = self._coerce(spec, values, user, partial=False)
        ts = now().isoformat(timespec="seconds")
        cols = ["created_at", "updated_at", *clean]
        cur = self.conn.execute(
            f"INSERT INTO {spec.entity} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [ts, ts, *clean.values()],
        )
        self._audit(spec, cur.lastrowid, user, "create", None, None, clean)
        self.conn.commit()
        return self.get_record(spec, user, cur.lastrowid)

    def update_record(self, spec: ToolSpec, user: User, rid: int, values: dict, action: str = "update",
                      comment: str | None = None) -> dict:
        self.require(spec, user, "update")
        before = self.get_record(spec, user, rid, raw=True)
        clean = self._coerce(spec, values, user, partial=True)
        if not clean:
            return self.get_record(spec, user, rid)
        sets = ", ".join(f"{k}=?" for k in clean)
        self.conn.execute(
            f"UPDATE {spec.entity} SET {sets}, updated_at=? WHERE id=?",
            [*clean.values(), now().isoformat(timespec="seconds"), rid],
        )
        self._audit(spec, rid, user, action, comment, {k: before[k] for k in clean}, clean)
        self.conn.commit()
        return self.get_record(spec, user, rid)

    def run_action(self, spec: ToolSpec, user: User, action_id: str, rid: int, comment: str | None) -> dict:
        action = next((a for a in spec.actions if a.id == action_id), None)
        if action is None:
            raise NotFound(f"action {action_id}")
        if not self._has_role(user, action.roles):
            raise Forbidden(f"{user.name} may not run '{action.label}'")
        if action.requires_comment and not (comment or "").strip():
            raise Invalid(f"'{action.label}' requires a comment")
        record = self._raw(spec, rid)  # action roles are the permission check; automation has no read role
        if not matches(action.only_when, record):
            raise Invalid(f"'{action.label}' is not available for this record")
        # actions may set protected fields on the user's behalf (like a plugin running as system)
        if action.set:
            sets = ", ".join(f"{k}=?" for k in action.set)
            self.conn.execute(
                f"UPDATE {spec.entity} SET {sets}, updated_at=? WHERE id=?",
                [*action.set.values(), now().isoformat(timespec="seconds"), rid],
            )
        self._audit(spec, rid, user, f"action:{action.id}", comment, {k: record[k] for k in action.set}, action.set)
        if action.webhook:
            payload = {"tool": spec.id, "record_id": rid, "action": action.id, "by": user.id,
                       "title": record[spec.title_field]}
            payload["signature"] = sign_payload(payload)
            self.conn.execute(
                "INSERT INTO integration_log (ts, tool, record_id, webhook, payload) VALUES (?,?,?,?,?)",
                (now().isoformat(timespec="seconds"), spec.id, rid, action.webhook, json.dumps(payload)),
            )
        self.conn.commit()
        return self._mask(spec, user, self._raw(spec, rid))

    def export_csv(self, spec: ToolSpec, user: User, view_id: str | None) -> str:
        self.require(spec, user, "export")  # the prvExportToExcel equivalent
        rows = self.list_records(spec, user, view_id)
        cols = [f.name for f in spec.stored_fields]
        lines = [",".join(cols)]
        for r in rows:
            lines.append(",".join('"' + str(r.get(c) if r.get(c) is not None else "").replace('"', '""') + '"' for c in cols))
        self._audit(spec, None, user, "export", f"{len(rows)} rows, view={view_id}", None, None)
        self.conn.commit()
        return "\n".join(lines)

    # ---- audit -----------------------------------------------------------------------
    def _audit(self, spec, rid, user, action, comment, before, after):
        self.conn.execute(
            "INSERT INTO audit_log (ts, tool, record_id, user_id, action, comment, before, after) VALUES (?,?,?,?,?,?,?,?)",
            (now().isoformat(timespec="seconds"), spec.id, rid, user.id, action, comment,
             json.dumps(before) if before is not None else None, json.dumps(after) if after is not None else None),
        )

    def audit(self, spec: ToolSpec, user: User, rid: int | None = None, limit: int = 50) -> list[dict]:
        self.require(spec, user, "read")
        sql = "SELECT * FROM audit_log WHERE tool=?"
        params: list = [spec.id]
        if rid is not None:
            sql += " AND record_id=?"
            params.append(rid)
        rows = self.conn.execute(sql + " ORDER BY id DESC LIMIT ?", [*params, limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["before"] = json.loads(d["before"]) if d["before"] else None
            d["after"] = json.loads(d["after"]) if d["after"] else None
            for key in ("before", "after"):
                if d[key]:
                    d[key] = self._mask(spec, user, d[key])
            out.append(d)
        return out

    def integrations(self, spec: ToolSpec, user: User, limit: int = 20) -> list[dict]:
        self.require(spec, user, "read")
        rows = self.conn.execute(
            "SELECT * FROM integration_log WHERE tool=? ORDER BY id DESC LIMIT ?", (spec.id, limit)
        ).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    # ---- policy checks -----------------------------------------------------------------
    def review(self, spec: ToolSpec, record: dict, viewer: User | None = None) -> dict:
        """Evaluate every policy check against a raw record. Pure; no permissions, no writes.

        Each result carries `evidence`: the record values the rule tested, masked for `viewer`
        (so evidence never leaks a column the viewer may not see) and the rule itself."""
        shown = self._mask(spec, viewer, {k: v for k, v in record.items() if k != "id"}) if viewer else dict(record)
        for f in spec.fields:
            if f.type == "boolean" and isinstance(shown.get(f.name), int):
                shown[f.name] = bool(shown[f.name])
        results = []
        verdict = "Cleared"
        for c in spec.checks:
            ok = matches(c.when, record)
            results.append({"id": c.id, "clause": c.clause, "title": c.title, "passed": ok,
                            "outcome": "pass" if ok else c.on_fail,
                            "detail": c.pass_text if ok else c.fail_text,
                            "rule": c.when,
                            "evidence": {f: shown.get(f) for f in filter_fields(c.when)}})
            if not ok:
                verdict = "Flagged" if c.on_fail == "flag" or verdict == "Flagged" else "Needs review"
        return {"verdict": verdict, "checks": results}

    def record_review(self, spec: ToolSpec, user: User, rid: int) -> dict:
        return self.review(spec, self.get_record(spec, user, rid, raw=True), viewer=user)

    def auto_review(self, spec: ToolSpec, user: User, actor: User, view_id: str | None = None) -> dict:
        """Apply the policy: cleared records get clear_action, flagged get flag_action, the rest wait for a human.

        Returns a per-record evidence report and writes one audit entry per record as `actor`,
        including the ones left for a human, so every decision cites its clauses and values."""
        self.require(spec, user, "update")
        ar = spec.auto_review
        if ar is None:
            raise Invalid(f"{spec.name} has no auto-review policy")
        rows = self.list_records(spec, user, view_id, extra=ar.scope)
        items: list[dict] = []
        for r in rows:
            raw = self._raw(spec, r["id"])
            res = self.review(spec, raw, viewer=user)
            title = str(raw[spec.title_field])
            failed = [c for c in res["checks"] if not c["passed"]]
            evidence = "; ".join(_cite(c) for c in res["checks"])
            if res["verdict"] == "Cleared" and ar.clear_action:
                outcome, action = "cleared", ar.clear_action
                reason = f"All {len(res['checks'])} checks passed under {ar.policy}: {evidence}"
                applied = self._try_action(spec, actor, action, raw["id"], f"Auto-cleared. {reason}. Run by {user.name}")
            elif res["verdict"] == "Flagged":
                blocking = [c for c in failed if c["outcome"] == "flag"]
                outcome, action = "escalated", ar.flag_action
                reason = (f"Mandatory control failed under {ar.policy}: "
                          + "; ".join(_cite(c) for c in blocking))
                applied = bool(action) and self._try_action(spec, actor, action, raw["id"],
                                                              f"Auto-escalated. {reason}. Run by {user.name}")
            else:
                outcome, action, applied = "review", None, False
                reason = (f"Not settled by {ar.policy}; needs a human on: "
                          + "; ".join(_cite(c) for c in failed))
                self._audit(spec, raw["id"], actor, "auto-review:hold", f"Left for human review. {reason}. Run by {user.name}", None, None)
            items.append({"record_id": raw["id"], "title": title, "outcome": outcome, "verdict": res["verdict"],
                          "action": action if applied else None, "reason": reason, "checks": res["checks"]})
        self._audit(spec, None, actor, "auto-review:run",
                    f"Reviewed {len(items)} record(s) in view '{view_id}' under {ar.policy}; "
                    f"{sum(i['outcome'] == 'cleared' for i in items)} cleared, "
                    f"{sum(i['outcome'] == 'escalated' for i in items)} escalated, "
                    f"{sum(i['outcome'] == 'review' for i in items)} left for human review. Run by {user.name}",
                    None, None)
        self.conn.commit()
        return {"policy": ar.policy, "actor": actor.id, "view": view_id, "items": items,
                "cleared": [i["title"] for i in items if i["outcome"] == "cleared"],
                "flagged": [i["title"] for i in items if i["outcome"] == "escalated"],
                "review": [i["title"] for i in items if i["outcome"] == "review"]}

    def ai_decision(self, spec: ToolSpec, rid: int) -> dict | None:
        """The automated action currently in force on a record: the latest state change was made by the
        auto-review actor and no human has acted or reset since. None when there is nothing to undo."""
        ar = spec.auto_review
        if ar is None:
            return None
        row = self.conn.execute(
            "SELECT * FROM audit_log WHERE tool=? AND record_id=? AND (action LIKE 'action:%' OR action='ai-reset') "
            "ORDER BY id DESC LIMIT 1",
            (spec.id, rid),
        ).fetchone()
        if row is None or row["user_id"] != ar.actor or not row["action"].startswith("action:"):
            return None
        return {"audit_id": row["id"], "action": row["action"][len("action:"):], "actor": row["user_id"],
                "ts": row["ts"], "before": json.loads(row["before"]), "after": json.loads(row["after"]),
                "reason": row["comment"]}

    def ai_decided(self, spec: ToolSpec, user: User) -> list[int]:
        """Records whose current state was set by the auto-review actor (bulk-reset candidates)."""
        self.require(spec, user, "read")
        ar = spec.auto_review
        if ar is None:
            return []
        ids = self.conn.execute(
            "SELECT DISTINCT record_id FROM audit_log WHERE tool=? AND user_id=? AND action LIKE 'action:%' "
            "AND record_id IS NOT NULL", (spec.id, ar.actor),
        ).fetchall()
        return [r["record_id"] for r in ids if self.ai_decision(spec, r["record_id"]) is not None]

    def reset_ai(self, spec: ToolSpec, user: User, rid: int, comment: str | None) -> dict:
        """Undo the automated decision on a record: restore the values it changed, audited as the human."""
        self.require(spec, user, "update")
        d = self.ai_decision(spec, rid)
        if d is None:
            raise Invalid("No automated decision to reset on this record")
        current = self._raw(spec, rid)
        restore = d["before"]
        sets = ", ".join(f"{k}=?" for k in restore)
        self.conn.execute(
            f"UPDATE {spec.entity} SET {sets}, updated_at=? WHERE id=?",
            [*restore.values(), now().isoformat(timespec="seconds"), rid],
        )
        note = f"Reset automated '{d['action']}' by {d['actor']} ({d['ts']}); restored {restore}."
        self._audit(spec, rid, user, "ai-reset", f"{note} {comment}".strip() if comment else note,
                    {k: current[k] for k in restore}, restore)
        self.conn.commit()
        return self._mask(spec, user, self._raw(spec, rid))

    def reset_ai_all(self, spec: ToolSpec, user: User, comment: str | None) -> dict:
        self.require(spec, user, "update")
        ids = self.ai_decided(spec, user)
        for rid in ids:
            self.reset_ai(spec, user, rid, comment)
        ar = spec.auto_review
        self._audit(spec, None, user, "ai-reset:all",
                    f"Reset {len(ids)} automated decision(s) by {ar.actor if ar else '?'}. {comment or ''}".strip(),
                    None, None)
        self.conn.commit()
        return {"reset": ids}

    def _try_action(self, spec: ToolSpec, actor: User, action_id: str, rid: int, comment: str) -> bool:
        try:
            self.run_action(spec, actor, action_id, rid, comment)
            return True
        except Invalid:
            return False  # record no longer in the action's state; leave it

    # ---- dashboard -------------------------------------------------------------------
    def dashboard(self, spec: ToolSpec, user: User) -> list[dict]:
        self.require(spec, user, "read")
        tiles = []
        for t in spec.dashboard:
            params: list = []
            where = compile_filter(t.filter, params)
            vf = t.value_field or t.field
            agg = {"count": "COUNT(*)", "sum": f"COALESCE(SUM({vf}),0)", "avg": f"COALESCE(AVG({vf}),0)"}[t.metric]
            if t.type == "kpi":
                v = self.conn.execute(f"SELECT {agg} FROM {spec.entity} WHERE {where}", params).fetchone()[0]
                tiles.append({**t.model_dump(), "value": v})
            elif t.type == "group":
                rows = self.conn.execute(
                    f"SELECT {t.field} AS k, {agg} AS v FROM {spec.entity} WHERE {where} GROUP BY {t.field} ORDER BY v DESC",
                    params,
                ).fetchall()
                tiles.append({**t.model_dump(), "data": [{"label": str(r["k"]), "value": r["v"]} for r in rows]})
            elif t.type == "series":
                since = (now() - timedelta(days=t.days)).date().isoformat()
                rows = self.conn.execute(
                    f"SELECT substr({t.date_field},1,10) AS k, {agg} AS v FROM {spec.entity} "
                    f"WHERE {where} AND {t.date_field} >= ? GROUP BY k ORDER BY k",
                    [*params, since],
                ).fetchall()
                by_day = {r["k"]: r["v"] for r in rows}
                days = [(now() - timedelta(days=i)).date().isoformat() for i in range(t.days - 1, -1, -1)]
                tiles.append({**t.model_dump(), "data": [{"label": d[5:], "value": by_day.get(d, 0)} for d in days]})
        return tiles

    def count(self, spec: ToolSpec) -> int:
        return self.conn.execute(f"SELECT COUNT(*) FROM {spec.entity}").fetchone()[0]
