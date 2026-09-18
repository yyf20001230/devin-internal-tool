# Devin vs Power Apps for fintech internal tools — evaluation and recommendation

*Context: a fintech engineering team that expects to build many internal back-office tools
(KYC queues, refund approvals, flag admin, dispute tracking, ...). This document is written
from the prototype in this repo, built in a few hours of Devin time across two rounds: a
schema-driven platform first, then the shell (sign-in, role-scoped boards, actionable
records), policy automation, embedded AI and the Devin Cloud "factory" layer.*

## 1. What Power Apps actually sells

Strip away the marketing and Power Apps is three things:

1. **A generated CRUD app over a data model.** Define a table; get grids, forms, views,
   a command bar, dashboards, search and mobile for free.
2. **Governance you didn't have to build.** Roles, column-level security, audit,
   DLP policies, tenant isolation, encryption, export controls, Entra ID sign-in.
3. **A maker who is not an engineer.** Ops can build the tool themselves; engineering
   is not the bottleneck.

Everything else (Power Automate, connectors, Copilot, Power BI) is the M365 gravity well
around those three.

## 2. What the prototype shows Devin can replicate

| Power Apps value | Prototype | Verdict |
|---|---|---|
| Generated CRUD from a schema | `tools/*.yaml` → tables, API, grid, form, views, command bar, tiles | **Replicated.** 4 tools = ~520 lines of YAML, 0 lines of tool-specific code. |
| Roles / row scope | `permissions:` + "assigned to me" views | Replicated for the common cases; no record-sharing or hierarchical BU model. |
| Column-level security | `visible_to:` — masked in grid, form, search, audit, export; writes rejected | Replicated, and arguably tighter (search can't leak a masked column). |
| Audit | before/after per change with user + comment | Replicated. |
| Export control (`prvExportToExcel`) | `permissions.export`, export itself is audited | Replicated. |
| Commands with business rules | `actions:` with role, state guard, comment, confirm | Replicated. |
| Power Automate | `webhook:` on an action | **Simulated only.** A real version is an outbox + worker (~1 session). |
| Dashboards | KPI / group / series tiles | Replicated for simple aggregates; no cross-table joins, no drill-through. |
| Entra ID sign-in | sign-in page + profile menu; identity is a header behind it | **UX built, protocol not.** Swapping the one `current_user` function for OIDC is a well-trodden ~half-session. |
| One model-driven app per persona | boards (`app:`) — a user sees only the boards their roles grant, never all three | Replicated. Tested: no identity sees every board. |
| Business rules / Copilot suggestions | policy clauses in `knowledge/*.md`, cited by `checks:`; `auto_review` clears or flags as the `devin-ai` identity | **Beyond Power Apps.** Automation is attributable, clause-cited and audited like a human. |
| Copilot in the app | case summary + plain-English queries compiled to a validated grid filter | **Beyond Power Apps** in control: only visible fields leave the process, output is schema-checked, every query is audited, works offline. |
| Mobile / offline | — | **Not built**, and not cheap. |
| Relationships between tables, lookups | — | **Not built.** Biggest functional gap for a real platform. |
| Non-engineer maker | `/new-tool` skill + playbook + repo knowledge | Different shape — see §3 and §6. |
| Tenant-grade controls (DLP, IP firewall, CMK) | — | Not applicable: no connectors to police; data never leaves your infra. |

The 4th tool (Chargeback Watchlist) is the key evidence: written from a one-paragraph
request following the playbook, it needed a YAML file and seed rows, nothing else, and
inherited every governance test automatically. It also picked up sign-in, boards, sortable
grid, detail-pane actions, AI summary and NL query when those were added to the shell later
— the only change to its YAML was one `icon:` line.

## 3. Honest comparison for this team

### Build cost

| | Power Apps | Devin-built platform |
|---|---|---|
| First tool | Days for a maker to learn; hours once fluent | This prototype: ~1h of Devin for platform + 3 tools; a few more hours for shell, policy automation and AI |
| Nth tool | Hours to a day, in Studio | `/new-tool`: one short Devin session + 15-30 min human PR review |
| Production-ready | Included (Microsoft runs it) | **Not free:** OIDC, Postgres, migrations, backups, relationships, outbox — realistically 4-8 Devin sessions plus 2-3 engineer-days of review and security sign-off. Packaging is done: one image + Kubernetes manifests (`make minikube`) that drop onto any cluster you already run |
| Ongoing licence | Per-user/per-app premium licences for anyone touching Dataverse or premium connectors; Managed Environments for the governance features that matter to a fintech | Hosting only (one pod + a volume on your existing cluster) + Devin usage |

At ~100+ ops users on premium licences the Power Apps run-rate is real money every year;
the Devin platform's cost is front-loaded and then near flat. Below ~30 users the licence
is cheap and this argument disappears.

### Maintenance burden

**Power Apps:** Microsoft patches the platform, but *you* absorb their roadmap — control
deprecations, "new look" migrations, connector changes, licence repackaging. Apps built by
someone who left become orphans nobody can read. ALM (solutions, environments, pipelines)
is workable but alien to an engineering team used to git.

**Devin platform:** you own the code, so you own the dependency upgrades, CVEs and hosting.
Mitigations: it is ordinary FastAPI/React that any engineer can read; there is *one*
codebase for N tools so a fix lands everywhere; and routine maintenance (bumps, test
fixes) is exactly the work Devin is good at. Realistic steady state: an hour or two of
review a month, more when a big framework upgrade lands.

The real maintenance risk is **platform ownership**: someone must own `server/` and `web/`.
If nobody does, this decays faster than Power Apps would.

### Security

**Power Apps:** mature and certified, but every control from the earlier research (DLP,
tenant isolation, IP firewall, column security, export privileges, CMK) is opt-in and
several are licence-gated. The default environment is wide open, and the citizen-developer
model is *designed* to route around engineering review — which is the thing a fintech's
change-control policy exists to prevent. Every connector a maker adds is a new data path
to assess.

**Devin platform:** data stays in your VPC and your Postgres; sign-in is your existing
IdP; secrets live in your vault; every change to a tool is a PR with a diff, a reviewer
and a CI run — the exact evidence your SOC 2 / PCI auditors already collect. Column
masking, audit and export control are enforced in one place and tested generically.
The costs: you have to *build* those controls (the prototype's auth is a stub), you have
to review AI-written code seriously, and Devin sessions need repo access — production data
should never be fed to the agent (seed data only, as here).

**AI inside the tools is the new attack surface**, and it is where a code-owned platform
earns its keep. In this prototype the model sees only fields the *current user* can already
see (a masked bank account never reaches the prompt), model output is validated against the
tool schema before it touches data, every query is written to the same audit log as a human
action, automation acts as a named service identity that cannot sign in, and the whole
feature degrades to deterministic rules when the key is absent. Each of those is a test, not
a tenant setting. With Copilot in Power Apps you get Microsoft's assurances but not a diff
you can point an auditor at.

Secrets never enter the repo or a prompt: `OPENAI_API_KEY` and `WEBHOOK_SIGNING_SECRET` are
read from the environment (Devin's secrets store in sessions, your vault in production),
`.env.example` lists names only, and a test asserts no committed file contains a signing key.

Net: for the specific concern raised earlier — merchant transaction data leaking — the
in-house platform has a smaller and more inspectable attack surface. Power Apps has more
controls; the in-house platform needs fewer.

### Opportunity cost of engineering time

This is the crux, and it cuts both ways.

- **Power Apps' promise** is that engineers never touch internal tools. In practice,
  fintech tools need custom APIs, premium connectors, PCF components and someone to debug
  Power Fx — so engineering gets pulled in anyway, but into a stack it doesn't know.
- **The Devin model** turns tool-building into *PR review*. Engineers spend 15-30 minutes
  per tool reading YAML and a screenshot rather than a day writing React. But the request
  still enters an engineering queue unless ops are allowed to open Devin sessions
  themselves (feasible with the playbook, and worth piloting).
- The hidden cost is the **first month**: hardening the platform is real engineering work
  that Power Apps would have skipped entirely.
- The counterweight is **policy automation**: once a rule is a clause in `knowledge/`, the
  platform clears or escalates the obvious cases itself. In the seeded KYC queue, 10 of 22
  open cases get a definitive verdict before an analyst opens it (2 cleared, 8 flagged for
  escalation with the breached clause attached); the other 12 are the ones that genuinely
  need judgment. That is ops time saved on every case, not engineering time saved once.

### Where Power Apps still clearly wins

- Non-engineer self-service with zero engineering involvement.
- Mobile app, offline, camera/barcode capture out of the box.
- Deep M365 integration (Teams, SharePoint, Outlook, Excel) and 1000+ connectors.
- Table relationships, lookups, business rules, and the compliance certification portfolio
  on day one.
- Nobody has to run a server.

### Where the Devin-built platform clearly wins

- Fits an engineering org's existing controls: git, code review, CI, IaC, SIEM.
- No per-user licence; no vendor roadmap risk; no "premium connector" surprises.
- Pixel-level UI freedom (the dark theme here is ~200 lines of CSS, swapped from a Power Apps-purple look in ten minutes).
- Sensitive data never leaves your infrastructure.
- Governance is *tested*, not configured: a new tool cannot ship with export wider than
  read, or a destructive action without a comment, because a test fails.
- AI features Power Apps + Copilot cannot do with this level of control: clause-cited
  automated review, case summaries, natural-language triage — all data-minimised, validated
  and audited in code you own.

## 4. Recommendation

**Build — but build the platform, not the apps.** For a fintech *engineering* team with a
working deploy pipeline, compliance obligations around change control, and a pipeline of
many similar back-office tools, a thin schema-driven platform like this one, with Devin as
the maker, is the better bet. Its economics improve with every tool and every user;
Power Apps' worsen with both.

Conditions — this recommendation flips if any of these are false:

1. **Someone owns the platform.** Name an engineer as owner of `server/` and `web/`.
   Without that, buy.
2. **The tools are back-office web tools.** If mobile, offline or field capture is a
   real requirement, buy (or use Power Apps just for those).
3. **Ops can live with a review step**, or you pilot letting them prompt Devin directly.
   If the requirement is truly "no engineer in the loop, ever", buy.
4. **The user count is meaningful** (≳ 50-100 licensed seats). Below that, Power Apps'
   licence cost is noise and its speed-to-first-app wins.

Suggested path:

- **Now:** harden this prototype — OIDC, Postgres, outbox for webhooks, table
  relationships. Estimate: 4-8 Devin sessions, ~3 engineer-days of review.
- **Pilot (4-6 weeks):** migrate two real tools; let one ops lead open Devin sessions
  using the playbook; measure request-to-production time and review minutes per tool.
- **Kill criteria:** if median review time per tool exceeds ~2 hours, or the platform
  owner spends more than a day a month on it, stop and buy.
- **Keep Power Apps in scope** for M365-adjacent, low-sensitivity employee forms
  (expenses, access requests) where its connectors are the whole point. Also evaluate
  Retool/Appsmith as a "buy" middle ground — code-friendly, but still a licence and still
  a place your data flows through.

## 5. What this prototype is not

It is a short proof, not a product: header auth behind a demo sign-in, SQLite, simulated
webhooks, additive-only migrations, no relationships, no file attachments, no notifications,
no i18n, no rate limiting, a rules-based AI fallback that is deliberately unambitious. Its
purpose is to show that the *shape* of Power Apps — schema in, governed app out — is small
enough to own, and that Devin can both build the platform and then act as the maker on top
of it.

## 6. How the Devin Cloud features map to what Power Apps gives you

Power Apps' "many apps, consistently" story rests on templates, the maker studio, an
environment strategy run by a Center of Excellence, managed environments and connection
references. Each has a Devin Cloud counterpart in this repo — and the counterpart is a file
under version control rather than a tenant setting.

| Power Apps | Devin Cloud feature | In this repo | What it buys the team |
|---|---|---|---|
| Template gallery → new app | **Skill / slash command** | `.devin/skills/new-tool/SKILL.md` | An engineer (or, in a pilot, an ops lead) types `/new-tool` with a paragraph; Devin produces YAML, seed, tests, screenshots and a PR that already follows auth, RBAC, audit and layout conventions. Tools 4–10 cost review time, not build time. |
| Maker in Studio + ALM pipeline | **Playbook** | `.devin/playbooks/new-internal-tool.md` | The full recipe — scaffold, SSO/RBAC, audit, policy clauses, AI checks, secrets, verify, PR — as a checklist Devin executes the same way every time. It is the process document a CoE would write, but runnable. |
| CoE standards, environment strategy, naming / security guidance | **Knowledge** | `knowledge/platform_conventions.md` (PLAT-x.y), `kyc_review_policy.md`, `refund_policy.md` | Design system, required audit fields, sensitive-data rules and business policy are stored once and cited by code (PLAT-2.3, KYC-2.1). No re-prompting; a convention change is a PR to one file. In Devin Cloud the same text is attached as org knowledge so it applies in every session. |
| Managed environment provisioning | **environment.yaml** | `environment.yaml` | Every session boots with deps, seeded DB, built UI and the app on :8000. Reproducible snapshot = no "works on my machine", and a new-tool session starts at step 1, not at setup. |
| Connection references / Key Vault-backed environment variables | **Secrets store** | `.env.example` (names), `os.environ` reads, `test_webhook_payloads_are_signed_with_env_secret_only` | DB creds, API keys and the webhook signing key never appear in prompts, YAML or commits. The fintech story: the agent that writes the tools never holds the credentials the tools use. |
| Copilot / AI Builder | **Devin as an in-product agent** (`devin-ai` service identity) | `auto_review`, `checks`, `server/ai.py` | Not a Devin Cloud feature per se, but the same idea one layer down: an attributable automation identity that acts inside the audit log, cites policy, and hands ambiguous work to humans. |

**Net effect on the recommendation.** These features address the strongest "buy" argument
— that only a low-code platform gives you *consistent* tools at volume without engineering
time. With the skill, playbook and knowledge in the repo, consistency is enforced by files
that are reviewed like any other code; with `environment.yaml` and the secrets store, each
new-tool session is cheap to start and safe to run. The remaining gap versus Power Apps is
not consistency or speed — it is *who is allowed to press the button*, which is an
organisational decision (§4, condition 3), not a technical one.
