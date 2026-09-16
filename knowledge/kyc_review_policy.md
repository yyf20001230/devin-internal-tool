# KYC Review Policy

Customer due diligence standard for onboarding business applicants. Owner: Head of Compliance. Version 3.2.

> Clauses marked with a code (e.g. KYC-2.1) are machine-readable: the KYC Review Queue cites them in its automated policy checks.

## 1. Scope

### KYC-1.1 Applicability
This policy applies to every business applicant onboarded through the merchant platform. No account may transact before a KYC decision is recorded.

### KYC-1.2 Four-eyes principle
A case may only be approved or rejected by a compliance lead. Analysts prepare cases, request documents and escalate; they do not decide.

## 2. Screening

### KYC-2.1 Sanctions and PEP screening
Every applicant, its directors and its ultimate beneficial owners are screened against sanctions lists and PEP databases at onboarding. Any match - including a partial name match - places the case under enhanced due diligence (EDD). A case with an open match must never be approved by automated processing.

### KYC-2.2 Adverse media
Adverse media screening is performed for all Medium and High risk applicants. Findings are recorded in the case notes.

## 3. Documentation

### KYC-3.1 Required documents
A case is document-complete only when 100% of the required set is received: certificate of incorporation, register of directors, UBO declaration, and proof of identity for each director and UBO holding 25% or more. Incomplete cases are not eligible for a decision; the analyst requests the missing items.

### KYC-3.2 Address verification
The registered and trading addresses must be verified against an independent source (company registry, utility bill or bank statement dated within 3 months). Self-declared addresses do not satisfy this clause.

## 4. Risk rating

### KYC-4.1 Risk bands
The risk engine assigns Low (score < 40), Medium (40-69) or High (70+). High-risk applicants always require review by a compliance lead and are worked before lower-risk cases in the queue.

### KYC-4.2 Straight-through threshold
Applicants scoring below 40 with no screening matches fall in the straight-through band and may be approved by automated policy checks (see section 6).

## 5. Service levels

### KYC-5.1 Decision SLA
Standard cases are decided within 48 hours of opening; EDD cases within 5 working days. Cases breaching SLA are surfaced in the "Breaching SLA in 4h" view and prioritised by risk.

## 6. Automated processing

### KYC-6.1 Automatic approval
A case may be approved without human review only when every automated check passes: no sanctions or PEP match (KYC-2.1), documents complete (KYC-3.1), address verified (KYC-3.2), risk Low or Medium (KYC-4.1) and score below 40 (KYC-4.2). The automated decision is recorded in the audit log with the clauses relied upon.

### KYC-6.2 Automatic escalation
Cases with a sanctions or PEP match are escalated to EDD automatically and re-rated High. Automation never rejects a case.

### KYC-6.3 Everything else waits for a human
Cases that fail a check other than screening remain in the queue with the failed checks shown to the reviewer, highest risk first.
