# Internal Tools Platform — a Power Apps alternative built with Devin

Prototype exploring how a fintech engineering team could use **Devin Cloud** to get the thing
Power Apps actually sells — *"describe a table, get a governed back-office app"* — while
keeping everything in a normal code repo, and adding the things Power Apps + Copilot cannot:
policy-aware automation and AI inside the tools.

```
tools/kyc_queue.yaml       ─┐
tools/refunds.yaml          ├─►  server/  FastAPI + SQLite: records, actions, dashboards, audit,
tools/feature_flags.yaml    │             export gating, policy checks, AI summary / NL query
tools/chargebacks.yaml     ─┘                     │
tools/_users.yaml            roles                ▼
knowledge/*.md               policies (citable)   web/  React shell: sign-in, role-scoped boards,
                                                        sortable grid, detail pane, dark theme

.devin/skills/new-tool/SKILL.md          /new-tool → scaffold a governed app
.devin/playbooks/new-internal-tool.md    full recipe: scaffold → SSO/RBAC → audit → policy → PR
environment.yaml                         reproducible Devin snapshot (deps, DB, seed, build, :8000)
.env.example                             secret *names* only; values live in Devin's secrets store
```

**One YAML = one app.** Fields, views, actions, dashboard tiles, permissions, policy checks and
auto-review are declared; `server/` and `web/` never change when a tool is added. The fourth
tool (Chargeback Watchlist) was added after the platform was finished: 92 lines of YAML, zero
platform code, all governance tests inherited.

## What it replicates from Power Apps

| Power Apps concept | Here |
|---|---|
| Dataverse table + columns | `fields:` → SQLite table (additive migrations on change) |
| Views / view selector | `views:` with filters, default sort (high risk first), "assigned to me"; decided records leave the queue |
| Model-driven form | auto-generated detail pane (single click), inline edit of permitted fields |
| Command bar | `actions:` in the pane with role, state guard, required comment, confirm dialog |
| Power Automate flow | `webhook:` on an action — payload HMAC-signed with `WEBHOOK_SIGNING_SECRET`, logged under *Integrations* |
| Dashboard tiles / charts | `dashboard:` KPI, group (donut / bars), series |
| Security roles + model-driven app per persona | `permissions:` per role; tools grouped into boards (`app:`); a user only sees boards their roles grant |
| Column-level security | `visible_to:` + `mask: last4` — masked in grid, sort, search, audit, export **and AI payloads** |
| `prvExportToExcel` privilege | `permissions.export` — exports are also audited |
| Auditing | `audit_log` with actor (human or `devin-ai`), action, comment, before/after |
| Entra ID sign-in | sign-in page + profile menu; demo header today, one function to swap for OIDC |
| Copilot in the app | case summary + plain-English queries compiled to the grid's own validated filter |
| Business rules | `knowledge/*.md` clauses cited by `checks:`; `auto_review` clears / flags with a clause reference |
| Templates / maker | `/new-tool` skill + playbook; Devin opens the PR |

## AI inside the tools

- **Case summary** at the top of every detail pane: headline, bullets, recommendation, built
  from the fields the current user can see, the policy check results and recent history.
- **Ask in plain English** above every grid: *"high-risk cases missing proof of address"*,
  *"refunds over 500 in the last week by reason"* → a validated filter on visible fields,
  rendered in the same grid, audited as `ai:query`.
- **Policy automation**: each record is checked against cited clauses (KYC-2.1, RF-4.1, …).
  All checks pass → `devin-ai` runs the tool's clear action; a `flag` check fails → escalates;
  anything else stays for a human, with the clauses shown in the pane.
- **Providers**: `OPENAI_API_KEY` present → OpenAI (`OPENAI_MODEL`, default `gpt-4o-mini`),
  strict-JSON, schema-validated, falls back automatically on error / quota. Absent → a
  deterministic rules provider, so the demo and tests never depend on a network call.
  Protected fields are dropped before anything leaves the process.

## Run it

```bash
pip install -r requirements.txt
python -m server.seed                                   # rebuild data.db with synthetic demo data
npm --prefix web ci && npm --prefix web run build       # static UI
uvicorn server.main:app --host 0.0.0.0 --port 8000      # UI + API on http://localhost:8000
python -m pytest -q                                     # 43 governance / policy / AI tests
```

Optional: copy `.env.example` to `.env` and set `OPENAI_API_KEY` for live LLM output and
`WEBHOOK_SIGNING_SECRET` for signed webhook payloads. In Devin Cloud these come from the
Secrets store; nothing in the repo ever holds a value.

Sign in as a demo identity — each sees only the boards its roles grant:

| User | Roles | Board(s) | What to look at |
|---|---|---|---|
| Priya | analyst | Compliance Ops | ID document / DOB masked; escalate / request docs; cannot approve or export |
| Marcus | compliance_lead, analyst | Compliance Ops | sees masked columns, approve / reject (comment), export, run policy review |
| Sofia | payments_ops | Payments Ops | refunds < 1,000; bank account masked; hold / approve small |
| Dan | finance, payments_ops | Payments Ops | approves > 1,000, sends to payout (signed webhook), exports |
| Lin | engineer | Release Control | DEV / UAT toggles, *requests* a PROD release |
| Amara | release_manager, engineer | Release Control | approves CR, flips PROD, kill switch |
| External Auditor | readonly | Compliance + Payments | sees everything, changes nothing, sensitive columns masked |

`Devin AI` is a service identity: it appears in audit history as the actor of automated
decisions and cannot sign in.

## Devin Cloud features used

| Feature | File | Power Apps analogue |
|---|---|---|
| Skill / slash command | `.devin/skills/new-tool/SKILL.md` | "Start from template" |
| Playbook | `.devin/playbooks/new-internal-tool.md` | The maker + ALM pipeline, as a checklist |
| Knowledge | `knowledge/platform_conventions.md` (+ policy docs) | Environment strategy / CoE standards |
| Declarative environment | `environment.yaml` | Managed environment provisioning |
| Secrets store | `.env.example` (names), `os.environ` (reads) | Connection references / Key Vault |

See `docs/EVALUATION.md` for the build-vs-buy assessment.
