---
name: new-tool
description: Scaffold a new governed internal tool (queue / dashboard / admin panel) on this platform from a one-paragraph request. Produces tools/<id>.yaml, seed data, policy checks, a passing test run, screenshots and a PR. Use when someone asks for "a queue for X", "a dashboard for Y", "an admin panel for Z", or types /new-tool.
---

# /new-tool — scaffold a governed internal app

This is the platform's equivalent of Power Apps' "start from template → new app".
Everything the request needs (auth, RBAC, column-level security, audit trail, dashboards,
webhooks, policy checks, embedded AI) already exists in the shared shell. Your job is to
**declare the tool, not build it**. If you find yourself editing `server/` or `web/`, stop
and re-read step 6.

## Inputs to collect (ask only if missing)

| Input | Example |
|---|---|
| Who asked, and which **board** it belongs to | Finance → `Payments Operations` |
| The **entity** and its fields | dispute id, merchant, amount, reason code, deadline, evidence status |
| **Who reads / writes / exports** (roles from `tools/_users.yaml`) | read: payments_ops, finance; export: finance |
| **State transitions** and who may perform them | submit evidence (ops), accept loss (finance, comment) |
| **Exception views** the team watches | due < 48h, missing evidence |
| **Questions the dashboard must answer** | how many open, value at risk, by reason code |
| Any **policy** the tool must enforce | "refunds ≤ 250 with an approved reason auto-clear" |

## Procedure

1. **Read the conventions first.** `knowledge/platform_conventions.md` (design system, required
   audit fields, sensitive-data rules), one existing tool (`tools/chargebacks.yaml` is the
   smallest), and `server/spec.py` for the schema. Do not re-derive conventions from memory.

2. **Write `tools/<tool_id>.yaml`.** Required sections, in this order:
   - `id`, `name`, `app` (one of the existing boards, or a new board name if a new persona),
     `description`, `entity`, `title_field`, `icon` (a name from `web/src/Icon.tsx`).
   - `permissions`: `read`, `write`, `export` (export ⊂ read — enforced by tests).
   - `fields`: every personal / financial column gets `visible_to: [...]` and, where a
     partial value is useful, `mask: last4`. Never store full PAN, full bank details, or
     document images — store a reference id.
   - `views`: an active queue (default sort puts the riskiest / most urgent first), an
     "assigned to me" view if there is an assignee, at least one exception view, and a
     decided/history view. Decided records must leave the active queue via the view filter.
   - `actions`: one per state transition. `destructive: true` + `requires_comment: true` for
     reject / loss / payout / production changes. External systems are `webhook:` actions
     under `https://hooks.internal/...` — never inline HTTP code.
   - `dashboard`: 3–4 KPI tiles, 1–2 group / series tiles. Group tiles that sum money need
     `value_field`.
   - Optional `policy` + `checks` + `auto_review` if the request names rules: write the rules
     as clauses in `knowledge/<policy>.md` (heading format `### CODE Title`, e.g. `### RF-2.2 ...`) and reference
     them by code. `on_fail: flag` escalates; default `review` leaves it for a human.

3. **Seed demo data** in `server/seed.py` — 20–200 rows, realistic distributions, dates relative
   to `now()`, and rows that exercise every policy branch (pass / review / flag).

4. **Run the governance suite:** `python -m pytest -q`. The tests are parameterised over every
   tool, so the new YAML is tested for role existence, export ⊂ read, destructive-needs-comment,
   masked columns, policy-clause validity and "no one sees every board" without new test code.
   Add a tool-specific test only for a business rule (a threshold, a routing decision).

5. **Build and screenshot:** `npm --prefix web run build && uvicorn server.main:app --port 8000`,
   then add a step to `scripts/screenshots.mjs` and run `node scripts/screenshots.mjs`.
   Check: monochrome icons, no emoji, dark theme, colour only on status / risk / SLA.

6. **Platform gaps.** If the request needs something the schema cannot express (a new field
   type, a new tile kind, a relationship), add it **generically** to `server/spec.py` /
   `server/engine.py` / `web/src` with a test, in a *separate* commit titled
   `platform: <capability>`. Never special-case one tool in platform code.

7. **Secrets.** Any credential the tool needs (a webhook signing secret, an upstream API key)
   is read from the environment only (`os.environ`) and documented in `.env.example` with a
   placeholder. Ask the requester to add it to Devin's secrets store; never paste it into a
   prompt, YAML, seed data or a commit.

8. **Open the PR** titled `tool: <Tool name>`. The description is for the requester, not an
   engineer: who can see what, which actions exist and who can run them, which webhooks fire,
   which policy clauses are enforced automatically, and the screenshots. Request review from
   the requester and one platform engineer.

## Guardrails

- Never put secrets, PAN, full bank details or customer PII in YAML, seed data or prompts.
- Never widen `permissions.read` to `readonly` on a tool with sensitive columns without
  `visible_to` on those columns.
- Never give a single demo identity access to every board.
- Stop and say so if the request implies sub-second latency, > 10 writes/s, mobile/offline,
  or a customer-facing surface — this platform is for internal back-office tools.

## Worked example

Request: *"Finance wants a chargeback watchlist: merchant, dispute id, amount, reason code,
deadline, evidence status. Ops should see it, only finance can accept a loss. Alert < 48h."*

Outcome: `tools/chargebacks.yaml` (92 lines), 36 seed rows in `server/seed.py`, zero platform
changes, 43/43 tests green, `docs/screens/08-chargebacks-4th-tool.png`, PR `tool: Chargeback
Watchlist`. Elapsed: one short Devin session.
