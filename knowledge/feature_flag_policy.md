# Feature Flag Release Policy

Change-control standard for feature flags that gate behaviour in production services. Owner: Head of Platform Engineering. Version 1.3.

> Clauses marked with a code (e.g. FF-2.1) are machine-readable: the Feature Flags panel cites them in its automated policy checks.

## 1. Scope

### FF-1.1 Applicability
This policy covers every flag in the flag store that any production service evaluates. Flags used only in DEV or UAT are exempt from change control but must still have a named owner.

### FF-1.2 Ownership
Every flag has an owning engineer. Flags whose owner has left the team are reassigned within one sprint; unowned flags may not be enabled in PROD.

## 2. Change control

### FF-2.1 Approved change request for PROD
A flag may only be enabled in PROD, or have its PROD rollout percentage increased, under an approved change request. Enabling PROD with a change request that is missing, pending or rejected is a policy breach and is surfaced in the "PROD on without approved CR" view.

### FF-2.2 Separation of duties
The engineer who requests a PROD release may not approve their own change request. Approval is reserved for release managers.

### FF-2.3 UAT before PROD
A flag must have been enabled in UAT before it is enabled in PROD. Emergency exceptions require a release manager's written justification in the change request.

## 3. Rollout

### FF-3.1 Progressive rollout
New PROD flags start at or below 10% rollout and are stepped up (10 → 25 → 50 → 100) with at least one business day between steps unless the change request states otherwise.

### FF-3.2 Kill switch
Every PROD flag must be switchable off without a deploy. A kill switch sets PROD off and rollout to 0, requires a written reason, and is logged in the audit trail and synced to the serving store immediately.

## 4. Hygiene

### FF-4.1 Stale flags
A flag at 100% PROD rollout for more than 30 days is stale. Stale flags are removed from code and the store within two sprints; they are listed in the "Stale" view for their owner.

### FF-4.2 Serving store is authoritative
Services read flags from the low-latency serving store, never from this panel. Every PROD change made here is pushed to the store by webhook; if the sync fails the change is reverted and the release manager notified.

## 5. Automated processing

### FF-5.1 What automation may do
Automated policy checks may flag a PROD breach (FF-2.1), an unowned PROD flag (FF-1.2) and stale flags (FF-4.1). Automation never enables a flag in PROD and never approves a change request.
