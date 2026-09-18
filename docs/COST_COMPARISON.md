# Annual cost: Power Apps vs the Devin-built platform (700 active users)

Talk-track numbers for the VP video. The Power Apps side is anchored on what the client **actually
pays today: $250,000 / year in total for 700 active users**. List prices (US, paid yearly, checked
September 2026) are used only to explain that number and for the Devin-side inputs; everything
marked *assumption* is an input you can change — the shape of the result does not.

## Headline

| Scenario (700 active back-office users, ~4 tools) | Year 1 | Steady state / year | $ per user / year |
|---|---:|---:|---:|
| **Power Apps — current spend** (licences + platform, as billed) | **$250k** | **$250k** | **~$357** |
| Power Apps incl. the maker / CoE time it needs *(if not already inside the $250k)* | ~$340k | ~$340k | ~$486 |
| **Devin-built platform** (this repo, hardened) | **~$115k** | **~$100k** | **~$143** |

**Saving: ~$150k a year (60%)** against the bill as it stands; ~$135k in Year 1 after hardening.
Licence-only view, because that is what people quote: Power Apps **$250,000 / year** vs Devin
**$0 per end user**. The Devin side has *no* per-seat cost — its money goes to people and hosting,
and is roughly flat whether you have 300 users or 3,000.

**Break-even**: the Devin platform's ~$100k/year all-in cost equals the current Power Apps
effective rate ($357 / user / year) at **~280 users**; at Premium list ($22 / user / month) it is
~380 users. Below that headcount, buy; above it, build gets cheaper with every seat while Power Apps
gets more expensive with every seat. At 700 you are 2.5× past the crossover.

## Power Apps — what $250k for 700 users buys

Source: microsoft.com Power Apps pricing page; Power Platform Licensing Guide (Nov 2025);
learn.microsoft.com pay-as-you-go meters and Managed Environments licensing.

| Line | List price | 700 users / year at list | Notes |
|---|---|---:|---|
| Power Apps Premium | $22 user/month | $184,800 | Unlimited apps per user. The $14 tier needs a 2,000-seat minimum, so it does not apply. |
| *or* Power Apps per app | $5 user/app/month (prepaid) | $42,000 per board in use | 3 boards for everyone = $126,000. Pay-as-you-go meter is $10 per *active* user/app/month. |
| Managed Environments (the governance you are buying it for) | included with Premium / per-app | $0 extra | But *every* active user in a managed environment must hold a Premium or per-app licence — no riding on M365 seeded rights. Microsoft starts in-app compliance nags June 2026. |
| Dataverse storage | 20 GB tenant + 250 MB/Premium user accrued | ~$5,000 | Prepaid add-on: $40/GB/month DB, $10/GB/month log (PAYG $48 and $12) once audit is on. |
| Copilot Studio / AI Builder (the "ask the policy" and AI-summary equivalents) | $200 per 25k messages/month; AI Builder credits | ~$5,000–$12,000 | Optional; without it you get form-level Copilot only. |
| Premium connectors, extra environments, licence over-provisioning | | remainder | Seats bought for people who are not active, plus add-ons, is typically where the gap to list goes. |
| **What is billed** | | **$250,000** | ≈ **$29.76 per active user per month**, i.e. ~35% above Premium list. Licences are the bulk of it and scale linearly with seats. |

Not in the $250k unless the client has already counted them:

| Line | Basis | Per year | Notes |
|---|---|---:|---|
| Makers + CoE admin (people) | 0.5 FTE loaded @ $180k | ~$90,000 | Someone still builds and maintains the apps and runs the Center of Excellence, DLP policies, environment strategy, licence reconciliation. Power Apps removes code, not work. |
| Rollout / re-platforming (one-off) | ~30 consultant/engineer days @ $1k | ~$30,000 | Already sunk for the existing estate; recurs for every new Managed Environment or major ALM change. |

Sensitivities: renegotiating to Premium list saves ~$65k; the $14 tier needs 2,000 seats. Headcount
cuts do not reduce the bill until renewal; every new active user adds ~$357.

## Devin-built platform — line items

Source: devin.ai/pricing (Team plan $80/month + $40/month per full seat; usage allowance per seat);
OpenAI list prices for `gpt-4o-mini` ($0.15 / $0.60 per 1M input/output tokens) and
`text-embedding-3-small`; hosting from AWS/GCP list; effort figures from `docs/EVALUATION.md`.

| Line | Basis | Per year | Notes |
|---|---|---:|---|
| End-user licences | — | **$0** | Sign-in via your existing Entra ID (OIDC); no per-seat fee anywhere in the stack. |
| Devin Team plan | $80/month + 3 full seats × $40 | $2,880 | Seats for the platform owner + two engineers who review tool PRs. |
| Devin extra usage *(assumption)* | ~1 new/changed tool per week, hardening, CI-fix sessions | ~$12,000 | Assumes ~$1k/month above the seat allowance; scales with how many tools you generate, not with users. |
| Hosting | 1 small managed Kubernetes (or ECS) service, managed Postgres with backups, load balancer | ~$12,000 | The prototype is a ~73 MB image per board; 700 back-office users is a light load. Minikube is dev-only. |
| OpenAI | 700 users × ~20 AI calls/day × 250 days ≈ 3.5M calls × ~1.8k tokens | ~$4,000 (list ≈ $1.4k; ~$14k at 10×) | ×10 safety margin shown. Embeddings are ~53 clauses per policy set — negligible. Deterministic fallback means AI outage ≠ tool outage. |
| Platform owner (people) | 0.25 FTE loaded @ $180k | ~$45,000 | The honest big line. Owns the YAML schema, the `/new-tool` playbook, upgrades, on-call. `EVALUATION.md` kill-criterion: if this exceeds ~1 day/month, revisit. |
| PR review of Devin-generated tools (people) | ~50 tools/changes × ~1.5 h × $110/h | ~$8,000 | The "review step" ops must accept instead of self-serve. |
| Security: annual pen-test / review of a bespoke internet-facing internal tool | | ~$15,000 | Power Apps gives you Microsoft's certifications on day one; here you buy the assurance yourself. |
| Year-1 hardening (one-off) | 4–8 Devin sessions + ~3 engineer-days review/security sign-off (`EVALUATION.md`) | ~$8,000–$15,000 | OIDC, Postgres + migrations, backups, outbox for webhooks, table relationships. |
| **Total** | | **~$115k yr 1, ~$100k/yr after** | ~70% of it is people and assurance, 0% is seats. |

Sensitivities: drop the platform owner to 0.1 FTE once stable → ~$75k/yr. Push AI usage 10× → +$12k.
Add 700 more users → +~$4k hosting and ~$2k OpenAI, nothing else.

## Scaling it: more users, more tools, more images

The cost model above is flat in seats because of how the platform is cut. Three axes, and what each
one costs:

| Growing… | Power Apps | Devin-built platform |
|---|---|---|
| **Users** 700 → 1,400 | +$250k (bill doubles: every active user needs a licence) | +~$6k (a slightly bigger pod / DB; no licence line exists) |
| **Tools** 4 → 20 | per-app: +$42k per board per year; Premium: $0 licences but +maker time per app | +$0 licences; ~90 lines of YAML each via `/new-tool` (Devin usage ≈ 1 session ≈ tens of dollars) + ~1.5 h engineer review; the platform code does not change |
| **Deployment units** 1 → N images | N environments = N × Managed Environment admin + licence reconciliation per environment | N × (`make minikube TOOL=<id>`) → ~$1–2k/yr hosting per extra image on a shared cluster, $0 licences |

**How the image split works (already in the repo).** One `Dockerfile`, one build arg: `--build-arg
TOOLS=kyc` produces `internal-tools-kyc:dev`, an image that ships only that board's YAML plus the
shared users, policies and UI. Each image runs as its own Deployment / Service / PVC (own SQLite file
and audit log) from a Kustomize overlay that is ~15 lines of copy-and-rename (`deploy/k8s/overlays/`).
Today there are four in minikube: the all-in-one plus KYC, refunds and feature flags, and a fifth
(chargebacks) was added as the worked example in under an hour. In production the same overlays
point at a real cluster and Postgres.

Why that matters for the bill:

- **Isolation is free.** Compliance, payments and release engineering can each have their own image,
  release cadence, data volume and on-call — the Power Apps equivalent is separate environments, each
  with its own licence pool and CoE overhead. Here it is another 73 MB image on the same cluster.
- **Cost scales with tools, not seats.** A new team wanting its own tool costs one Devin session, one
  PR review and (optionally) one overlay. At 700 users that is ~$500 of marginal cost against ~$42k
  per year for the same board on Power Apps per-app.
- **One codebase, N images.** The images differ only in which `tools/*.yaml` they carry; a platform
  fix (RBAC, masking, audit, AI) is one PR, one rebuild, `make split-redeploy` — no per-app solution
  export/import or per-environment ALM pipeline.
- **The ceiling is engineering, not licensing.** Going from N images to N+1 never triggers a licence
  tier, a seat minimum or a Managed Environment rule. The only thing that grows is the platform
  owner's review queue — which is the 0.25 FTE line and the pilot's kill-criterion.

## What to say in the video (30 seconds)

- "Today Power Apps costs **$250k a year for 700 active users — about $357 a head**, before anyone
  builds anything new. The platform Devin built comes to about **$100k a year all-in**, and **none of
  that is per-seat** — it's a quarter of an engineer, hosting, and an annual security review. That is a
  **~$150k a year saving, 60%**."
- "The crossover is under **300 users**. We are at 700 — two and a half times past it — and every seat
  we add widens the gap."
- "It scales the other way too: each team gets its **own image** — KYC, refunds, flags run as separate
  deployments today from one codebase — and a fifth board costs one Devin session and a PR review,
  not $42k of per-app licences."
- "The one number on the Build side you should be sceptical of is the **0.25 FTE platform owner**. If
  that person ends up spending more than a day a month, the saving shrinks fast — that's why it's a
  kill-criterion in the pilot."
- "What you don't get for the $100k: Microsoft's compliance certificates, mobile/offline, 1,000+
  connectors. If any of those is a hard requirement, the price comparison is moot."

## Caveats

- The $250k is the client's reported total; it is ~35% above Premium list for 700 seats, so it likely
  includes add-ons or seats for inactive users. Ask for the licence reconciliation before quoting it as
  "licences only".
- Maker / CoE people cost (~$90k) is shown separately because it may or may not be inside the $250k;
  the Devin column always includes its people cost.
- Devin usage above the seat allowance is not published as a flat rate on the pricing page; the $12k
  is an assumption to be confirmed with Cognition for the expected session volume.
- Per-image hosting figures assume the images share one small managed cluster; a dedicated cluster
  per team would add ~$8–10k each.
- People costs use a $180k fully-loaded engineer; change one number and both columns move together.
