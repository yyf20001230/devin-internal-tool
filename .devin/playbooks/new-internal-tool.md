# Playbook: build a new internal tool from a request

Use this when someone in ops / compliance / finance / engineering asks for a new
internal tool ("we need a queue for X", "a dashboard for Y", "an admin panel for Z").
In Power Apps this is the "maker" sitting in the studio; here it is Devin opening a PR.

## Procedure

1. **Read the request and the existing tools.** Read `tools/*.yaml` and `server/spec.py`
   so the new tool follows the same conventions (field types, view naming, action guards).
   Do not touch `server/` or `web/` unless the request needs a capability the platform
   genuinely lacks - if it does, add it generically, never as a special case for one tool.

2. **Write `tools/<tool_id>.yaml`.** It must contain:
   - `fields` with sensible `type`s; mark anything personal or financial
     (`visible_to: [..]`, `mask: last4`) so column-level security applies from day one.
   - At least: an "all / open" view, an "assigned to me" view if there is an assignee,
     and one exception view (breaches, over-limit, missing approval).
   - `actions` for every state transition the requester described. Any action that
     rejects, deletes, pays out or touches production must have `requires_comment: true`
     and `destructive: true` where appropriate. Anything that calls another system is a
     `webhook:` action, not code.
   - `dashboard` with 3-4 KPI tiles and 1-2 group/series tiles answering the questions
     the requester actually asked ("how many...", "how much...", "by whom...").
   - `permissions` where `export` is a strict subset of `read`. Roles must exist in
     `tools/_users.yaml`; add a role there if the request introduces a new persona.

3. **Seed demo data** in `server/seed.py` (20-200 rows, realistic distributions, dates
   relative to `now()`), so the dashboard is meaningful on first open.

4. **Run the checks.** `python -m pytest -q` - the governance tests are parameterised over
   every tool, so the new YAML is tested without writing new tests. Add a tool-specific
   test only for business rules (e.g. an amount threshold routing to a different approver).

5. **Screenshot it.** `python -m server.seed && uvicorn server.main:app --port 8000` plus
   `npm --prefix web run dev`, then `node scripts/screenshots.mjs` (or add a step for the
   new tool). Attach the screenshot to the PR.

6. **Open a PR** titled `tool: <Tool name>` describing, for a non-engineer reviewer: who
   can see what, which actions exist and who can run them, and which webhooks fire.
   Request review from the person who asked for the tool AND one engineer.

## Guardrails

- Never put secrets, PAN, full bank details or raw customer PII in seed data or YAML.
- Never widen `permissions.read` to include `readonly` on a tool holding sensitive
  columns without also setting `visible_to` on those columns.
- Never add a `webhook` to a host that is not under `hooks.internal` without asking.
- If the request implies sub-second latency, high write volume (>10 writes/s), or a
  customer-facing surface, stop and say so: this platform is for internal back-office
  tools, the same boundary Power Apps has.

## Example request -> outcome

> "Finance wants a chargeback watchlist: merchant, dispute id, amount, reason code,
> deadline to respond, evidence status. Ops should see it, only finance can accept a
> loss. Alert when < 48h to deadline."

Outcome: `tools/chargebacks.yaml` (fields incl. `deadline`, views `open`,
`due-48h`, `mine`; actions `submit_evidence` (webhook), `accept_loss` (finance,
comment, destructive); tiles: open count, due < 48h, value at risk, by reason code),
seed rows in `server/seed.py`, green `pytest`, screenshot, PR.
