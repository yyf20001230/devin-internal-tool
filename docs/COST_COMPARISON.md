# Annual cost: Power Apps vs the Devin-built platform (1,000 users)

Talk-track numbers for the VP video. List prices checked September 2026 (US, paid yearly);
everything marked *assumption* is an input you can change — the shape of the result does not.

## Headline

| Scenario (1,000 back-office users, ~4 tools) | Year 1 | Steady state / year | $ per user / year |
|---|---:|---:|---:|
| **Power Apps Premium** (the plan Microsoft steers 1,000-seat orgs to) | **~$395k** | **~$365k** | ~$365 |
| Power Apps per-app, every user uses all 3 boards | ~$310k | ~$280k | ~$280 |
| Power Apps per-app, each user uses 1 board (best case) | ~$190k | ~$160k | ~$160 |
| **Devin-built platform** (this repo, hardened) | **~$115k** | **~$100k** | ~$100 |

Licence-only view, because that is what people quote: Power Apps Premium **$264,000 / year**
(1,000 × $22 × 12) vs Devin **$0 per end user**. The Devin side has *no* per-seat cost — its money
goes to people and hosting, and is roughly flat whether you have 300 users or 3,000.

**Break-even**: the Devin platform's ~$100k/year all-in cost equals Power Apps *licences alone* at
**~380 users** on Premium, ~560 users on per-app × 3 boards, and ~1,670 users on per-app × 1 board
(conservative for Build — it ignores the Power Apps people cost). Below those headcounts, buy; above,
build gets cheaper every year while Power Apps gets more expensive with every seat.

## Power Apps — line items

Source: microsoft.com Power Apps pricing page; Power Platform Licensing Guide (Nov 2025);
learn.microsoft.com pay-as-you-go meters and Managed Environments licensing.

| Line | Price | 1,000 users / year | Notes |
|---|---|---:|---|
| Power Apps Premium | $22 user/month | **$264,000** | Unlimited apps per user. The $14 tier needs a 2,000-seat minimum, so it does not apply. |
| *or* Power Apps per app | $5 user/app/month (prepaid) | $60,000 per board in use | 3 boards for everyone = $180,000. Pay-as-you-go meter is $10 per *active* user/app/month. |
| Managed Environments (the governance you are buying it for) | included with Premium / per-app | $0 extra | But *every* active user in a managed environment must hold a Premium or per-app licence — no riding on M365 seeded rights. Microsoft starts in-app compliance nags June 2026. |
| Dataverse storage | 20 GB tenant + 250 MB/Premium user accrued | ~$0 | 270 GB pooled is plenty for these tools. Prepaid add-on: $40/GB/month DB, $10/GB/month log (PAYG meters $48 and $12) if you turn audit on. Budget ~$5k. |
| Copilot Studio / AI Builder (the "ask the policy" and AI-summary equivalents) | $200 per 25k messages/month; AI Builder credits | ~$5,000 (up to ~$12,000) | Optional; without it you get form-level Copilot only. |
| Makers + CoE admin (people) | 0.5 FTE loaded @ $180k | ~$90,000 | Someone still builds and maintains the apps and runs the Center of Excellence, DLP policies, environment strategy, licence reconciliation. Power Apps removes code, not work. |
| Year-1 rollout: environment strategy, DLP, ALM pipelines, security review | ~30 consultant/engineer days @ $1k | ~$30,000 one-off | Typical Managed Environments + CoE starter kit set-up. Often bundled with a partner. |
| **Total, Premium** | | **~$395k yr 1, ~$365k/yr after** | Licences are ~72% of it and scale linearly with seats. |

Sensitivities: negotiate Premium to ~$18 → $216k licences (total ~$315k). Grow to 2,000 seats
and the $14 tier kicks in → $336k licences for twice the users. Headcount cuts do not reduce the bill
until renewal.

## Devin-built platform — line items

Source: devin.ai/pricing (Team plan $80/month + $40/month per full seat; usage allowance per seat);
OpenAI list prices for `gpt-4o-mini` ($0.15 / $0.60 per 1M input/output tokens) and
`text-embedding-3-small`; hosting from AWS/GCP list; effort figures from `docs/EVALUATION.md`.

| Line | Basis | Per year | Notes |
|---|---|---:|---|
| End-user licences | — | **$0** | Sign-in via your existing Entra ID (OIDC); no per-seat fee anywhere in the stack. |
| Devin Team plan | $80/month + 3 full seats × $40 | $2,880 | Seats for the platform owner + two engineers who review tool PRs. |
| Devin extra usage *(assumption)* | ~1 new/changed tool per week, hardening, CI-fix sessions | ~$12,000 | Assumes ~$1k/month above the seat allowance; scale with how many tools you generate. |
| Hosting | 1 small managed Kubernetes (or ECS) service, managed Postgres with backups, load balancer | ~$12,000 | The prototype is a single ~75 MB image; 1,000 back-office users is a light load. Minikube is dev-only. |
| OpenAI | 1,000 users × ~20 AI calls/day × 250 days ≈ 5M calls × ~1.8k tokens | ~$5,000 (list ≈ $2k; ~$20k at 10×) | $2k at list for gpt-4o-mini; ×10 safety margin shown. Embeddings are ~53 clauses per policy set — negligible. Deterministic fallback means AI outage ≠ tool outage. |
| Platform owner (people) | 0.25 FTE loaded @ $180k | ~$45,000 | The honest big line. Owns the YAML schema, the `/new-tool` playbook, upgrades, on-call. `EVALUATION.md` kill-criterion: if this exceeds ~1 day/month, revisit. |
| PR review of Devin-generated tools (people) | ~50 tools/changes × ~1.5 h × $110/h | ~$8,000 | The "review step" ops must accept instead of self-serve. |
| Security: annual pen-test / review of a bespoke internet-facing internal tool | | ~$15,000 | Power Apps gives you Microsoft's certifications on day one; here you buy the assurance yourself. |
| Year-1 hardening (one-off) | 4–8 Devin sessions + ~3 engineer-days review/security sign-off (`EVALUATION.md`) | ~$8,000–$15,000 | OIDC, Postgres + migrations, backups, outbox for webhooks, table relationships. |
| **Total** | | **~$115k yr 1, ~$100k/yr after** | ~70% of it is people and assurance, 0% is seats. |

Sensitivities: drop the platform owner to 0.1 FTE once stable → ~$75k/yr. Push AI usage 10× → +$18k.
Add 1,000 more users → +~$5k hosting, nothing else.

## What to say in the video (30 seconds)

- "At a thousand users Power Apps Premium is **$264k a year in licences before anyone builds anything**;
  all-in it's about **$365k**. The platform Devin built is about **$100k a year all-in**, and **none of that
  is per-seat** — it's a quarter of an engineer, hosting, and an annual security review."
- "The crossover is around **400 users**. Under that, buy. Over that, every seat you add makes Build cheaper
  relative to Buy."
- "The one number on the Build side you should be sceptical of is the **0.25 FTE platform owner**. If that
  person ends up spending more than a day a month, the saving shrinks fast — that's why it's a kill-criterion
  in the pilot."
- "What you don't get for the $100k: Microsoft's compliance certificates, mobile/offline, 1,000+ connectors.
  If any of those is a hard requirement, the price comparison is moot."

## Caveats

- Power Apps prices are US list, paid yearly; EA/CSP discounts of 15–30% are common at this seat count.
- Power Apps per-app can be *cheaper* than Build at 1,000 users if each user truly only ever opens one
  app — check real usage before assuming Premium.
- Devin usage above the seat allowance is not published as a flat rate on the pricing page; the $12k
  is an assumption to be confirmed with Cognition for the expected session volume.
- People costs use a $180k fully-loaded engineer; change one number and both columns move together.
