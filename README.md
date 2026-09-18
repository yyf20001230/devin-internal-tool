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
  anything else stays for a human, with the clauses shown in the pane. Every run returns an
  evidence report (outcome, action, clause codes per record); opening the record shows each
  check, the values it was judged on, the rule and the clause text. Humans with `update` rights
  can undo an automated decision per record (**Reset AI decision**) or all at once
  (`POST /ai-reset`): the pre-review values are restored and the reset is audited as the human,
  never over a later human decision.
- **Ask the policy** in every detail pane: *"can I approve this without the missing document?"*
  → the question (plus the record's non-protected fields) is matched against the knowledge
  base, the top clauses are handed to the model, and the answer cites them (`KYC-1.2`, …).
  Clicking a citation shows the clause text, the source document and the similarity score.
  Audited as `ai:ask` with the clauses retrieved and the ones the answer relied on.
- **Knowledge base**: the AI never reads the Markdown files directly. At startup each
  `knowledge/*.md` is split into one chunk per clause, embedded (OpenAI
  `text-embedding-3-small`) and stored in SQLite (`kb_chunks`); summaries and answers retrieve
  from that index (`server/kb.py`). Unchanged clauses are not re-embedded (content hash).
  Without an API key or on quota errors the index runs on a local hashed-TF-IDF vector so
  search still works offline. `GET /api/knowledge/status` shows backend, model and chunk count;
  `GET /api/knowledge/search?q=…` searches it; `POST /api/knowledge/reindex` reloads the docs.
- **Providers**: `OPENAI_API_KEY` present → OpenAI (`OPENAI_MODEL`, default `gpt-4o-mini`),
  strict-JSON, schema-validated, falls back automatically on error / quota. Absent → a
  deterministic rules provider, so the demo and tests never depend on a network call.
  Protected fields are dropped before anything leaves the process.

## Maintaining the knowledge base (for ops, compliance and engineering)

The AI in each board only knows what is in these files — if a rule is not written here it
cannot cite it, clear on it or answer questions about it. When policy changes, change the file:

| New information about… | Edit this file | Clause prefix | Used by |
|---|---|---|---|
| KYC / onboarding review, sanctions, documents, risk bands | `knowledge/kyc_review_policy.md` | `KYC-` | KYC Review Queue |
| Refunds, approval limits, fraud holds, refund windows | `knowledge/refund_policy.md` | `RF-` | Refunds Dashboard |
| Feature flags, change requests, rollouts, kill switch | `knowledge/feature_flag_policy.md` | `FF-` | Feature Flags |
| Platform / design / audit conventions for *building* tools | `knowledge/platform_conventions.md` | `PLAT-` | Devin when scaffolding new tools |

**How to write it so the AI can use it**

1. One rule per clause, under a level-3 heading with a code: `### RF-2.4 Partial refunds`.
   Codes are `PREFIX-section.number`; never reuse or renumber an existing code — add a new one
   (`RF-2.4`, `RF-2.5`…) so old audit entries keep pointing at the right rule.
2. Write the rule as a complete, standalone paragraph in plain language, with the concrete
   thresholds, roles and time limits ("below 1,000", "finance", "60 days"). Each clause is
   retrieved on its own, so it must make sense without the clauses around it.
3. Say who may do what, and keep an explicit "What automation may do" clause per policy so
   reviewers can see the boundary the automated checks are allowed to work within.
4. Writing the clause is enough for the AI to *cite* it (summaries, Ask the policy). To have
   it *enforced*, add a `checks:` entry in the tool's YAML that cites the code
   (`clause: RF-2.4`, `when: {amount: {lt: 1000}}`) — that is what lets `devin-ai` clear or
   escalate a record. The server refuses to start if a check cites a clause that does not
   exist, so a typo cannot ship.
5. Open a pull request. Policy is code: a compliance lead reviews the diff, CI runs the
   governance tests (`python -m pytest -q`), and the change is traceable in git history.
6. Once merged and deployed the server re-indexes on startup; on a running instance call
   `POST /api/knowledge/reindex` (any signed-in user) to pick the change up immediately.
   Only the clauses whose text changed are re-embedded.

A new policy area (say, payouts) is a new file `knowledge/payout_policy.md` with its own
prefix (`PO-`); the loader picks up every `.md` in the folder automatically, and a new tool
references it with `auto_review: {policy: payout_policy}`. Don't put merchant, customer or
identity data in these files — they are policy, they are sent to the embedding provider, and
they are visible to every signed-in user.

## Run it locally

**Prerequisites: Python 3.10+ and Node 18+.** macOS ships Python 3.9 with the Xcode
command-line tools, which is too old, and has no Node — install both first:

```bash
brew install python@3.12 node        # macOS (https://brew.sh); Linux: apt install python3.12 python3.12-venv nodejs npm
python3.12 --version && node --version
```

```bash
git clone https://github.com/yyf20001230/devin-internal-tool && cd devin-internal-tool
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
npm --prefix web ci && npm --prefix web run build       # static UI → web/dist
export OPENAI_API_KEY=sk-...                            # optional: live LLM + OpenAI embeddings
python -m server.seed                                   # rebuild data.db with synthetic demo data
uvicorn server.main:app --host 0.0.0.0 --port 8000      # UI + API on http://localhost:8000
```

Open http://localhost:8000 and pick a demo identity. Without `OPENAI_API_KEY` everything
still works on the offline rules engine and lexical embeddings (the AI panels say "rules"
instead of "LLM"). `python -m pytest -q` runs the 52 governance / policy / AI / KB tests.

After changing anything under `web/src`, run `npm --prefix web run build` again and hard-refresh
the browser; the server serves the built files. Alternatively `npm --prefix web run dev` starts a
hot-reloading dev server on :5173 that proxies the API to :8000.

Optional: copy `.env.example` to `.env` and set `OPENAI_API_KEY` for live LLM output and
`WEBHOOK_SIGNING_SECRET` for signed webhook payloads. In Devin Cloud these come from the
Secrets store; nothing in the repo ever holds a value.

**Working a queue fast:** rows show only what you need to triage; open a record for the full
detail in a three-tab pane: **Summary** (AI case summary + Approve / Reject / Request more info,
environment switches on boolean fields, plus any secondary actions), **Policy check** (the clause
checks and the Ask-the-policy box) and **Details** (every field, edit, audit trail). Which action
fills each decision slot comes from `decision: approve|reject|info` on the tool's YAML actions; a
boolean field becomes a switch when an action `set`s it (flags: UAT / PROD). Decision buttons only
show when the record is in a state where they apply, and grey out only for a missing role. ↑/↓ move
through the queue, Enter opens the record, Esc closes it. Acting on an open record advances to
the next one in the queue.

Sign in as a demo identity — each sees only the boards its roles grant:

| User | Roles | Board(s) | What to look at |
|---|---|---|---|
| Priya | analyst | Compliance Ops | ID document / DOB masked; escalate / request docs; cannot approve or export |
| Marcus | compliance_lead, analyst | Compliance Ops | sees masked columns, approve / reject (comment), export, run policy review |
| Sofia | payments_ops | Payments Ops | refunds < 1,000; bank account masked; approve small / request info |
| Dan | finance, payments_ops | Payments Ops | approves > 1,000, sends to payout (signed webhook), exports |
| Lin | engineer | Release Control | UAT / PROD switches and kill switch; PROD without an approved CR is *flagged* (FF-2.1), not blocked |
| Amara | release_manager, engineer | Release Control | approves / rejects change requests |
| External Auditor | readonly | Compliance + Payments | sees everything, changes nothing, sensitive columns masked |

`Devin AI` is a service identity: it appears in audit history as the actor of automated
decisions and cannot sign in.

## Run it on minikube (Docker + Kubernetes)

The same app ships as one container image (`Dockerfile`: Node builds the UI, a slim Python
image serves API + UI on :8000) plus Kubernetes manifests in `deploy/k8s/` (Kustomize:
Namespace, ConfigMap, PVC for the SQLite file, Deployment, NodePort Service). The pod seeds the
demo data the first time its volume is empty, then keeps it across restarts.

**Prerequisites:** Docker, [minikube](https://minikube.sigs.k8s.io/docs/start/), kubectl
(`brew install minikube kubectl`).

```bash
export OPENAI_API_KEY=sk-...   # optional; omit for offline rules/lexical mode
make minikube                  # start cluster → build image → deploy → create secret → print URL
```

`make minikube` prints the app URL (`minikube service internal-tools -n internal-tools --url`);
open it and sign in as usual. Other targets:

| Target | What it does |
|---|---|
| `make image` | `docker build` + `minikube image load` (no registry). Docker Hub rate-limiting you? `make image BASE_REGISTRY=mirror.gcr.io/library` |
| `make deploy` | `kubectl apply -k deploy/k8s` and wait for the rollout |
| `make redeploy` | after a code change: rebuild the image and roll the pod |
| `make secret` | creates/updates the `internal-tools-secrets` Secret from `OPENAI_API_KEY` / `WEBHOOK_SIGNING_SECRET` in your shell and restarts the pod |
| `make reseed` | wipes the SQLite file on the volume and restarts → fresh demo data |
| `make status` / `make logs` / `make url` | inspect |
| `make down` / `make destroy` | remove the app / delete the cluster |

After a code change: `make redeploy` (the Deployment uses `Recreate` because SQLite on a
single ReadWriteOnce volume wants one writer). Config lives in `deploy/k8s/configmap.yaml`
(`SEED=auto|always|never`, model names); secrets never touch the repo — the Secret is created
from your environment, exactly as Devin Cloud injects them from its Secrets store.

For a real cluster, swap the NodePort for an Ingress in front of your IdP (OIDC / Entra ID
replaces the demo `X-User` header) and point `DB_PATH` at a managed database volume or replace
SQLite with Postgres.

## Devin Cloud features used

| Feature | File | Power Apps analogue |
|---|---|---|
| Skill / slash command | `.devin/skills/new-tool/SKILL.md` | "Start from template" |
| Playbook | `.devin/playbooks/new-internal-tool.md` | The maker + ALM pipeline, as a checklist |
| Knowledge | `knowledge/platform_conventions.md` (+ policy docs, indexed into the in-app KB) | Environment strategy / CoE standards |
| Declarative environment | `environment.yaml` | Managed environment provisioning |
| Secrets store | `.env.example` (names), `os.environ` (reads) | Connection references / Key Vault |

See `docs/EVALUATION.md` for the build-vs-buy assessment.
