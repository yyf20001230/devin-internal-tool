# Internal Tools Platform — a Power Apps alternative built with Devin

Prototype (built in ~1h) exploring how a fintech engineering team could use **Devin Cloud**
to get the thing Power Apps actually sells — *"describe a table, get a governed back-office
app"* — while keeping everything in a normal code repo.

```
tools/kyc_queue.yaml      ─┐
tools/refunds.yaml         ├─►  server/ (FastAPI + SQLite)  ─►  web/ (React, dark theme)
tools/feature_flags.yaml  ─┘        generic API: records, actions, dashboard, audit, export
tools/_users.yaml                   roles + column-level security + audit log
.devin/playbooks/new-internal-tool.md   ← Devin is the "maker": request → YAML → PR
```

**One YAML = one app.** Fields, views, commands, dashboard tiles and permissions are all
declared; `server/` and `web/` never change when a tool is added. The three fintech tools
here (KYC review queue, refunds dashboard, feature-flag admin) are ~90 lines of YAML each.

## What it replicates from Power Apps

| Power Apps concept | Here |
|---|---|
| Dataverse table + columns | `fields:` → SQLite table (additive migrations on change) |
| Views / view selector | `views:` with filters (`{status: [A,B]}`, `{sla_due: {lt: now+4h}}`), "assigned to me" |
| Model-driven form | auto-generated record pane |
| Command bar / ribbon buttons | `actions:` with role, state guard, required comment, confirm dialog |
| Power Automate flow | `webhook:` on an action (simulated; logged in the *Outbound integrations* tile) |
| Dashboard tiles / charts | `dashboard:` KPI, group (donut / bars), series |
| Security roles | `permissions:` read / create / update / export per role |
| Column-level security (field security profiles) | `visible_to:` + `mask: last4` — masked in grid, form, search, audit and export |
| `prvExportToExcel` privilege | `permissions.export` — exports are also audited |
| Auditing | `audit_log` with before/after per change, action, user, comment |
| Entra ID sign-in | stub `X-User` header + role switcher (would be OIDC at the proxy) |
| Maker in Power Apps Studio | Devin + `.devin/playbooks/new-internal-tool.md` |

## Run it

```bash
pip install fastapi "uvicorn[standard]" pyyaml pytest httpx
python -m server.seed                          # rebuild data.db with demo data
uvicorn server.main:app --port 8000 --reload   # API
npm --prefix web install && npm --prefix web run dev   # UI on http://localhost:5173 (proxies /api)
python -m pytest -q                            # governance tests, parameterised over every tool
```

Use the "Sign in as" dropdown (top right) to switch personas:

| User | Roles | What to look at |
|---|---|---|
| Priya | analyst | KYC only; ID document / DOB masked; cannot Approve or Export |
| Marcus | compliance_lead | sees masked columns, can Approve/Reject (comment required), Export |
| Sofia | payments_ops | refunds < 1,000 only; bank account masked |
| Dan | finance | approves > 1,000 with comment, sees full account, exports |
| Lin | engineer | flags in DEV/UAT, can *request* a PROD release (webhook) |
| Amara | release_manager | approves CR, flips PROD, kill switch |
| Auditor | readonly | sees everything, changes nothing, everything sensitive masked |

## Adding a tool

Write `tools/<id>.yaml`, add seed rows, run `pytest`. Or paste the request into a Devin
session with the playbook above and review the PR. See `docs/EVALUATION.md` for the
honest build-vs-buy assessment.
