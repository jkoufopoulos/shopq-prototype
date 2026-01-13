---
description: Fetch and analyze recent Cloud Run logs for classification and digest debugging
---

Fetch the last 2 hours of Cloud Run logs from production, focusing on:
1. Classification decisions (type, domain, attention)
2. Verifier verdicts (confirm/reject)
3. Digest generation logs (importance, entities, weather, narrative)
4. Error messages and exceptions
5. Confidence scores and reasoning

Use gcloud to fetch logs from:
- Service: mailq-api (production environment)
- Project: mailq-467118
- Time range: last 2 hours
- Focus on logs containing: [Importance], [Entity], [Weather], [Classification], [Verifier], ERROR, WARNING

Format the logs in a readable way that shows:
- Timestamp
- Log level
- Log message
- Any structured data (JSON fields)

Group logs by category:
1. **Classification Logs** - Show classification decisions with confidence scores
2. **Digest Logs** - Show importance scoring, entity extraction, narrative generation
3. **Verifier Logs** - Show when verifier was triggered and its verdicts
4. **Errors** - Any exceptions or failures

After fetching, analyze the logs for:
- Patterns in low-confidence classifications
- Common verifier triggers
- Digest generation issues (missing entities, weather failures, etc.)
- Any anomalies or unexpected behavior

Provide actionable insights on what might need debugging or improvement.
