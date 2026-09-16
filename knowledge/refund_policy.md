# Refund Policy

Approval standard for merchant-initiated and customer-initiated refunds across card, bank transfer and wallet rails. Owner: Head of Payments Operations. Version 2.4.

> Clauses marked with a code (e.g. RF-2.2) are machine-readable: the Refunds Dashboard cites them in its automated policy checks.

## 1. Scope

### RF-1.1 Applicability
This policy covers every refund request raised against a settled transaction. Refunds against unsettled transactions are voided at the processor and are out of scope.

### RF-1.2 Approval limits
Payments operations may approve refunds below 1,000 (in transaction currency). Refunds of 1,000 or more require finance sign-off with a written justification. Only finance may release approved refunds to payout.

## 2. Eligibility

### RF-2.1 Evidence
A refund must reference the original transaction and state a reason from the approved list. Reasons that depend on a customer claim ("Goods not received", "Customer request") require the merchant's evidence to be reviewed before approval.

### RF-2.2 Automatically approvable reasons
"Duplicate charge", "Pricing error" and "Subscription cancelled" are objectively verifiable from ledger data and are eligible for automatic approval when the other automated checks pass.

### RF-2.3 Refund window
Refunds are processed within 60 days of the original purchase. Requests outside the window require a documented exception approved by finance.

## 3. Fraud controls

### RF-3.1 High-risk refunds
Refunds rated High risk by the fraud engine, and all "Fraud reversal" refunds, are held for the fraud team. They must not be approved automatically and should be put on hold pending investigation.

### RF-3.2 Refund velocity
A customer receiving a third or later refund within 90 days is a refund-abuse indicator. Such requests are flagged for reviewer attention and the merchant may be asked for supporting information.

### RF-3.3 Destination account
Refunds to a destination that differs from the original funding source require finance approval regardless of amount.

## 4. Automated processing

### RF-4.1 Straight-through limit
Refunds below 250 that pass every automated check - eligible reason (RF-2.2), inside the window (RF-2.3), not high risk (RF-3.1), normal velocity (RF-3.2) - are approved automatically. The approval is recorded in the audit log with the clauses relied upon; finance still releases the payout (RF-1.2).

### RF-4.2 Human review
Any refund failing a check remains in "Awaiting approval" with the failed checks shown. Flagged refunds (RF-3.1, RF-3.2) are shown first.
