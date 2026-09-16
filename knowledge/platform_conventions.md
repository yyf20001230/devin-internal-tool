# Internal Tools Platform Conventions

Org conventions every generated tool must follow. Owner: Platform Engineering. Devin reads this before scaffolding a tool (`/new-tool`) so requesters never have to restate them.

> Clauses carry codes (PLAT-x.y) so PR reviews and Devin's own checks can cite them, the same way tools cite KYC-x.y and RF-x.y.

## 1. Design system

### PLAT-1.1 Theme
Near-black canvas (`--bg`), dark-grey panels, white primary text, muted secondary text, hairline borders. One blue accent for primary actions and chart series. No purple, no gradients, no brand imagery.

### PLAT-1.2 Colour carries meaning only
Colour is reserved for state: green = approved / cleared / on, amber = pending / needs review / due soon, red = rejected / flagged / overdue / production risk. Everything else is monochrome. A reviewer should be able to scan a grid and see only the cells that need attention.

### PLAT-1.3 Icons
Monochrome 24px line icons from `web/src/Icon.tsx` only. No emoji, no filled glyphs, no per-tool icon files. Every tool declares `icon:` in its YAML; every action may declare `icon:` or falls back to an inferred one (approve → check, reject → x, escalate → arrow-up, request docs → file).

### PLAT-1.4 Layout
Every tool renders in the shared shell: left nav grouped by board, header with view chips, Dashboard / Records tabs, single-click detail pane on the right (380px) with AI summary → policy checks → actions → details → history. Tools do not ship their own layout.

## 2. Access control

### PLAT-2.1 Boards follow personas
Tools are grouped into boards (`app:`) by persona: Compliance Operations, Payments Operations, Release Control. A user sees only the boards their roles grant; no single identity may have every board (enforced by `test_no_single_person_sees_every_board`).

### PLAT-2.2 Roles are declared, not implied
`permissions.read/create/update/export` list roles from `tools/_users.yaml`. `export` must be a subset of `read`. New roles need a one-line description in `_users.yaml` and a reason in the PR.

### PLAT-2.3 Sensitive columns are masked by default
Any field holding personal identifiers, document numbers, bank or card details, or dates of birth must set `visible_to:` to the narrowest role set, and `mask: last4` where a partial value helps. Masked values never leave the server in list, search, sort, export or AI payloads.

### PLAT-2.4 Four-eyes on money and production
Actions that move money, reject a customer, accept a loss, or change PROD require `requires_comment: true` and are restricted to the approving role, not the preparing role.

### PLAT-2.5 Authentication
The demo uses an `X-User` header behind a sign-in page. Production wires Entra ID / OIDC in `server/main.py::current_user` and maps group claims to roles; nothing else changes.

## 3. Audit and integrations

### PLAT-3.1 Required audit fields
Every write is recorded with: `ts` (UTC ISO-8601), `tool`, `record_id`, `user_id` (human or `devin-ai`), `action` (`create`, `update`, `action:<id>`, `ai:query`), `comment`, `before`, `after`. The platform writes these automatically; tools may not bypass `Engine.run_action`.

### PLAT-3.2 Automated decisions are attributed
Anything decided by policy automation runs as the `devin-ai` service identity, cites the clause codes it relied on in the comment, and is visible in the same history as human decisions. Automation may only clear when every configured check passes, and may only flag where a check declares `on_fail: flag`.

### PLAT-3.3 Outbound integrations
External side effects are declared as `webhook:` on an action under `https://hooks.internal/...`. Payloads carry tool, record id, action, actor and title only — never the full record — and are HMAC-signed with `WEBHOOK_SIGNING_SECRET` from the environment.

## 4. Data handling

### PLAT-4.1 No real merchant data in the repo
Seed data is synthetic and generated in `server/seed.py`. Fixtures, screenshots and tests never contain production records.

### PLAT-4.2 Data minimisation for AI
Before any external model call, the record is reduced to the fields the current user can already see, protected fields are dropped, and only relevant policy clauses and the last few audit entries are attached. Model output is validated against the tool schema (fields, operators, choice values) before it is executed. Every query is audited as `ai:query`.

### PLAT-4.3 Secrets
Credentials are read from environment variables only and documented in `.env.example` with empty placeholders. In Devin Cloud they live in the Secrets store. They never appear in YAML, seed data, prompts, tests or commits.

## 5. Delivery

### PLAT-5.1 One YAML per tool
A tool is `tools/<id>.yaml` plus seed rows. If a request needs a capability the schema lacks, it is added generically to the platform in a separate `platform:` commit with a test — never as a special case for one tool.

### PLAT-5.2 Definition of done
`python -m pytest -q` green, `npm --prefix web run lint` clean, screenshots refreshed in `docs/screens/`, PR description written for the requester (who sees what, which actions, which webhooks, which clauses are automated).
