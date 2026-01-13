# Trust Threats & Mitigations (MVP framing)

| User fear | Mitigation now (MVP) | Planned (NEXT) |
|---|---|---|
| "Dev stole money / read financial emails" | Read-only by default; store metadata only; no payment actions; phishing/fraud guardrails elevate but never act. | Encryption at rest; anomaly alerts on scope escalation. |
| "Dev emailed someone fraudulently" | No `gmail.send` scope; we don't send drafts or emails. | Agent features require separate, explicit opt-in scopes. |
| "Emails leaked to other users" | Per-user scoping on every table; deterministic DTOs; no cross-tenant queries. | Row-level security tests; periodic multi-tenant audits. |
| "Emails were deleted" | No destructive Gmail ops; only reversible labeling if user enables it. | Safe-mode guard (block destructive endpoints) + audit log. |
| "Emails leaked publicly (logs/backups)" | No body storage; logs redact PII; tracking DB is ephemeral. | Encrypt DB + backups; retention policy enforced by job. |

*Principle:* prove value with read-only; make writes optional, transparent, and reversible; protect user data by minimizing what we store.
