# Key decisions — one page

**What I built.** A schema-driven internal-tools platform: one YAML file per tool
(`tools/*.yaml`, ~600 lines for four boards) is turned by a generic FastAPI + React runtime
(~3,300 lines) into a governed CRUD app — grid, views, detail pane, actions, dashboard tiles,
role permissions, column masking, audited export, audit log, webhook, and AI features grounded
in Markdown policy documents. Plus the "factory": a `/new-tool` skill, a playbook and repo
knowledge so a one-paragraph request from ops becomes a PR. It ships as one container image,
or one image per board, on Kubernetes (`make minikube` / `make split`).

## Why this scope

The brief said "replicate Power Apps". Power Apps is Dataverse + canvas + connectors + Copilot +
mobile + a marketplace; replicating that is a multi-year product. So I asked what its *value*
is for this customer and landed on one sentence: **declare a data model, get a governed CRUD
app for free.** Everything I built serves that sentence; everything else (mobile, offline,
connectors, table relationships) I deliberately left out and wrote down as gaps in
`docs/EVALUATION.md` rather than half-building.

The test of the scope was the fourth tool. If adding a board needs platform code, the thesis
fails. Chargebacks was written from one paragraph, following the playbook: 94 lines of YAML,
zero new Python or TypeScript, and it inherited sign-in, boards, masking, audit, policy checks
and AI when those landed later (one `icon:` line changed). That is the evidence I would point at.

## Decisions and tradeoffs

**Generic runtime + YAML, not generated code per tool.** Devin could have generated a bespoke
app each time. I chose one interpreter so that a fix or a new control (masking in AI payloads,
say) lands in every tool at once and is covered by the same 47 tests. Cost: the YAML schema is
a real API that has to be versioned, and anything the schema can't express needs a platform
change. I accepted that because the alternative recreates the Power Apps orphan problem.

**Policy as Markdown clauses, checks that cite them.** Rules live in `knowledge/*.md` with
IDs (KYC-3.2, RF-1.2); `checks:` and the AI reviewer reference them. Compliance can change a
rule via PR without touching code. Cost: two places (clause text and check logic) can drift;
I mitigated with a test that every cited clause exists.

**Advisory, not blocking, governance.** Early on I greyed out disallowed buttons. The user
found it confusing and it hid *why*. I switched to: every decision is clickable; a breach shows
the clauses, demands a comment, and is written to the audit log as an override. This matches how
fintech ops actually works (humans overrule policy with a paper trail). Cost: a bad actor can
click through — which is why the audit log, not the button, is the control.

**AI is bounded by the same permissions.** The model only receives fields the current user
can see, its output is validated against the tool schema, every call is audited, automation
acts as a named `devin-ai` identity, and everything degrades to deterministic rules without a
key. This made the OpenAI outage I hit during the build a non-event, and it is the argument
for owning the code: each bound is a test, not a tenant setting.

**SQLite + `X-User` header, on purpose.** Prototype-grade persistence and auth kept the
2-hour budget on the thesis. Both are single-function swaps (Postgres, OIDC) and are the first
items in the hardening plan — and the SQLite threading bug I shipped on Python 3.12 is a fair
reminder that "prototype-grade" has real costs.

**One Dockerfile, N images.** Per-board images (`--build-arg TOOLS=kyc`) with their own
Deployment/PVC give teams isolation without per-environment licences. Chosen over one shared
instance because the cost story (`docs/COST_COMPARISON.md`) turns on cost scaling with tools,
not seats.

## What I would tell you I got wrong or skipped

Table relationships/lookups are the biggest functional gap for a real platform. The webhook is
simulated (no outbox/retry). Auth is a stub. The break-even numbers rest on one assumed Devin
usage rate. And the recommendation — build the platform, not the apps — only holds if someone
owns `server/` and `web/`; without an owner, buy.
