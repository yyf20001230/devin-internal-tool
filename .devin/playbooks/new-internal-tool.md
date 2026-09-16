# Playbook: spin up a new internal tool

Use when ops / compliance / finance / engineering asks for a new back-office tool
("a queue for X", "a dashboard for Y", "an admin panel for Z"). In Power Apps this is a maker
sitting in the studio; here it is a Devin session that ends in a reviewed PR.

The playbook is the *whole* recipe — scaffold, SSO/RBAC, audit, policy automation, AI,
secrets, environment, PR. Most steps are already done by the platform; the checklist exists
so nothing is skipped and so tools 4–10 cost the same as tool 3.

**Inputs:** the request (one paragraph is enough), the requester, and their board.
**Output:** a PR titled `tool: <Name>` with screenshots, green tests, and a requester-facing description.

---

## 0. Boot

The Devin environment (`environment.yaml`) already installed deps, seeded `data.db`, built the
UI and can start `uvicorn server.main:app --port 8000`. Secrets (`OPENAI_API_KEY`,
`WEBHOOK_SIGNING_SECRET`) arrive as environment variables from the Devin Secrets store; if a
new tool needs another credential, ask the requester to add it there and reference it by name.
Never ask for the value in chat.

Read, in order: `knowledge/platform_conventions.md`, `tools/chargebacks.yaml`,
`server/spec.py`. These are the org conventions — do not restate or reinterpret them.

## 1. Scaffold the tool (the Power Apps "template → app" step)

Invoke `/new-tool` (`.devin/skills/new-tool/SKILL.md`). It produces:

- `tools/<id>.yaml` — entity, fields with column-level security, views (active queue with
  risk/urgency-first sort, mine, exceptions, history), actions with guards, dashboard tiles,
  `icon`, `app` (board), `permissions`.
- Seed rows in `server/seed.py` that exercise every state and policy branch.

Layout, grid, forms, sorting, search, detail pane and dashboards come from the shared shell.
There is no per-tool UI code.

## 2. Wire authentication and RBAC (SSO)

- **Identity:** the shell already gates every request through `current_user` in
  `server/main.py`. The prototype accepts a demo header behind the sign-in page; production
  replaces that one function with OIDC / Entra ID token validation and maps group claims →
  roles. No tool changes.
- **Roles:** every role in `permissions` must exist in `tools/_users.yaml`. Add a new role
  only for a genuinely new persona, with a one-line description.
- **Boards:** set `app:` so the tool appears on the right board. Confirm with
  `test_no_single_person_sees_every_board` that no identity now sees everything.
- **Columns:** `visible_to` + `mask: last4` on every personal / financial field (PLAT-2.3).
- **Four-eyes:** approving / paying / rejecting / PROD actions are `requires_comment: true`
  and limited to the approving role (PLAT-2.4).

## 3. Add the audit trail

Already automatic: create / update / action / AI-query writes go through `Engine` and land in
`audit_log` with the required fields (PLAT-3.1). Your job is to *check* it, not build it:

- Open the tool, run one action per role, and confirm each appears in the pane's History
  with actor, comment, before/after.
- If an action has external side effects, declare `webhook:` under `https://hooks.internal/`;
  the platform signs the payload with `WEBHOOK_SIGNING_SECRET` and logs it under Integrations.

## 4. Encode policy as knowledge + automated checks (optional, when rules exist)

If the requester names rules ("auto-approve under 250 with an approved reason", "never
auto-clear a sanctions hit"):

1. Write them as citable clauses in `knowledge/<policy>.md` (`### CODE-x.y Title` + text).
2. Add `checks:` to the YAML citing those codes, with `on_fail: flag` for breaches and the
   default `review` for "a human must look".
3. Add `auto_review:` naming `clear_action` / `flag_action` (marked `system: true` so humans
   cannot run them). The `devin-ai` identity clears only when every check passes (PLAT-3.2).
4. Seed rows for pass / review / flag, and assert the counts in a tool-specific test.

The detail pane then shows each clause, its outcome and its text; humans review only what
automation could not settle.

## 5. Embedded AI (already available; verify it behaves)

Case summaries and natural-language queries work for any tool through `server/ai.py`.
Verify for the new tool:

- Ask two plain-English questions in the grid; the returned filter must only reference
  fields the user can see (PLAT-4.2) and appear as an `ai:query` audit entry.
- Open a record; the summary must not contain a masked value.
- With `OPENAI_API_KEY` absent, both fall back to deterministic rules — the demo must still
  work offline.

## 6. Verify

```bash
python -m pytest -q                     # governance suite, parameterised over every tool
npm --prefix web run lint               # tsc
npm --prefix web run build && uvicorn server.main:app --port 8000 &
APP_URL=http://localhost:8000 node scripts/screenshots.mjs   # add a step for the new tool
```

Check the screenshots against PLAT-1.x: dark theme, monochrome icons, colour only on state.

## 7. Open the PR

Title `tool: <Name>`. Description for the requester, not for an engineer:

- Who can see which board and columns; what is masked from whom.
- Each action, who may run it, and whether it needs a comment.
- Which webhooks fire and what they carry.
- Which policy clauses are enforced automatically and which need a human.
- Screenshots.
- Any new secret name the deployment needs (name only).

Request review from the requester and one platform engineer. If you had to touch `server/` or
`web/`, put that in a separate commit `platform: <capability>` with a test, and say why in
the PR.

---

## Guardrails

- Never put secrets, PAN, full bank details or customer PII in YAML, seed data, prompts or
  commits (PLAT-4.1, PLAT-4.3).
- Never special-case one tool in platform code (PLAT-5.1).
- Never let automation clear a record when any check is unresolved, or flag without a
  clause that says `on_fail: flag`.
- Never add a webhook host outside `hooks.internal` without asking.
- Stop and say so if the request implies sub-second latency, > 10 writes/s, mobile/offline
  or a customer-facing surface — same boundary Power Apps has.

## Example

> "Finance wants a chargeback watchlist: merchant, dispute id, amount, reason code, deadline,
> evidence status. Ops should see it, only finance can accept a loss. Alert when < 48h."

Outcome: `tools/chargebacks.yaml` (92 lines: views `open`, `due48`, `mine`, `closed`;
actions `submit_evidence` (webhook), `accept_loss` (finance, comment, destructive); tiles:
open, due < 48h, value at risk, by reason code), 36 seed rows, **zero platform changes**,
43/43 tests, `docs/screens/08-chargebacks-4th-tool.png`, PR `tool: Chargeback Watchlist`.
