# MailQ Tracking Database - SQL Guide

## Connection

```bash
# Basic connection
sqlite3 data/mailq_tracking.db

# With formatted output
sqlite3 -column -header data/mailq_tracking.db

# One-line query
sqlite3 data/mailq_tracking.db "SELECT COUNT(*) FROM email_threads"
```

## Database Schema

### **email_threads** table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `thread_id` | TEXT | Gmail thread ID |
| `message_id` | TEXT | Gmail message ID |
| `from_email` | TEXT | Sender email address |
| `subject` | TEXT | Email subject |
| `received_date` | TEXT | When email was received |
| `email_type` | TEXT | Type: notification, receipt, event, etc. |
| `type_confidence` | REAL | Confidence score (0-1) |
| `domains` | TEXT | JSON array: ["finance", "shopping"] |
| `domain_confidence` | TEXT | JSON object: {"finance": 0.95} |
| `attention` | TEXT | action_required or none |
| `relationship` | TEXT | from_contact or from_unknown |
| `importance` | TEXT | critical, time_sensitive, or routine |
| `importance_reason` | TEXT | Why this importance level? |
| `decider` | TEXT | rule, llm, detector, or cache |
| `verifier_used` | BOOLEAN | Was verifier LLM called? |
| `verifier_verdict` | TEXT | confirm or reject |
| `verifier_reason` | TEXT | Why verifier accepted/rejected |
| `entity_extracted` | BOOLEAN | Was entity extracted? |
| `entity_type` | TEXT | flight, event, deadline, etc. |
| `entity_confidence` | REAL | Entity extraction confidence |
| `entity_details` | TEXT | JSON with entity data |
| `in_digest` | BOOLEAN | Included in any part of digest? |
| `in_featured` | BOOLEAN | In featured/narrative section? |
| `in_orphaned` | BOOLEAN | In orphaned section? |
| `in_noise` | BOOLEAN | In noise summary? |
| `noise_category` | TEXT | Which noise category? |
| `summary_line` | TEXT | Actual line in digest |
| `summary_linked` | BOOLEAN | Does line have entity link? |
| `session_id` | TEXT | Unique session identifier |
| `timestamp` | TEXT | When tracked (ISO format) |

## Example Queries

### **1. Session Overview**

```sql
-- List all sessions
SELECT
    session_id,
    COUNT(*) as thread_count,
    MIN(received_date) as earliest_email,
    MAX(received_date) as latest_email
FROM email_threads
GROUP BY session_id
ORDER BY session_id DESC;
```

### **2. Importance Breakdown**

```sql
-- Show importance distribution for latest session
SELECT
    importance,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM email_threads WHERE session_id = (SELECT MAX(session_id) FROM email_threads)), 1) as percentage
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
GROUP BY importance
ORDER BY count DESC;
```

### **3. Top Importance Reasons**

```sql
-- What patterns trigger different importance levels?
SELECT
    importance,
    importance_reason,
    COUNT(*) as occurrences
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
GROUP BY importance, importance_reason
ORDER BY importance, occurrences DESC;
```

### **4. Entity Extraction Analysis**

```sql
-- Entity extraction success rate by importance
SELECT
    importance,
    COUNT(*) as total,
    SUM(entity_extracted) as extracted,
    ROUND(SUM(entity_extracted) * 100.0 / COUNT(*), 1) as success_rate_pct
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
GROUP BY importance;
```

### **5. Entity Extraction Failures**

```sql
-- Important emails that failed entity extraction
SELECT
    importance,
    subject,
    email_type,
    attention,
    importance_reason
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
    AND entity_extracted = 0
    AND importance != 'routine'
ORDER BY importance, subject;
```

### **6. Verifier Usage**

```sql
-- When was verifier used and what did it decide?
SELECT
    subject,
    email_type,
    type_confidence,
    decider,
    verifier_verdict,
    verifier_reason
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
    AND verifier_used = 1
ORDER BY verifier_verdict;
```

### **7. Digest Inclusion Breakdown**

```sql
-- Where did emails end up in the digest?
SELECT
    CASE
        WHEN in_featured = 1 THEN 'Featured'
        WHEN in_orphaned = 1 THEN 'Orphaned'
        WHEN in_noise = 1 THEN 'Noise'
        ELSE 'Not Included'
    END as digest_section,
    COUNT(*) as count
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
GROUP BY digest_section;
```

### **8. Noise Category Breakdown**

```sql
-- What types of noise emails?
SELECT
    noise_category,
    COUNT(*) as count
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
    AND in_noise = 1
GROUP BY noise_category
ORDER BY count DESC;
```

### **9. Unlinked Summary Lines**

```sql
-- Summary lines without entity links (validation failures)
SELECT
    subject,
    summary_line,
    entity_extracted,
    entity_type
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
    AND summary_line IS NOT NULL
    AND summary_linked = 0;
```

### **10. Classification Decision Breakdown**

```sql
-- How were emails classified? (rule vs LLM vs detector)
SELECT
    decider,
    COUNT(*) as count,
    ROUND(AVG(type_confidence), 3) as avg_confidence,
    SUM(verifier_used) as times_verified
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
GROUP BY decider
ORDER BY count DESC;
```

### **11. Critical Emails**

```sql
-- All critical emails with full details
SELECT
    subject,
    from_email,
    importance_reason,
    entity_type,
    summary_line,
    in_featured,
    verifier_used
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
    AND importance = 'critical'
ORDER BY received_date;
```

### **12. Search by Sender**

```sql
-- Find all emails from specific sender
SELECT
    session_id,
    subject,
    importance,
    email_type,
    in_featured,
    summary_line
FROM email_threads
WHERE from_email LIKE '%amazon%'
ORDER BY timestamp DESC
LIMIT 20;
```

### **13. Time-Sensitive Without Entities**

```sql
-- Time-sensitive emails that didn't get entities (potential issues)
SELECT
    subject,
    email_type,
    importance_reason,
    attention
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
    AND importance = 'time_sensitive'
    AND entity_extracted = 0;
```

### **14. Confidence Analysis**

```sql
-- Distribution of confidence scores
SELECT
    CASE
        WHEN type_confidence >= 0.95 THEN 'Very High (0.95+)'
        WHEN type_confidence >= 0.85 THEN 'High (0.85-0.95)'
        WHEN type_confidence >= 0.75 THEN 'Medium (0.75-0.85)'
        ELSE 'Low (<0.75)'
    END as confidence_bucket,
    COUNT(*) as count,
    SUM(verifier_used) as verified
FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads)
GROUP BY confidence_bucket
ORDER BY confidence_bucket;
```

### **15. Full Thread Audit**

```sql
-- Complete history for a specific thread
SELECT *
FROM email_threads
WHERE thread_id = 'YOUR_THREAD_ID'
ORDER BY timestamp DESC;
```

## Advanced Queries

### **Cross-Session Trends**

```sql
-- Compare entity extraction across sessions
SELECT
    session_id,
    COUNT(*) as total_threads,
    SUM(entity_extracted) as extracted,
    ROUND(SUM(entity_extracted) * 100.0 / COUNT(*), 1) as success_rate
FROM email_threads
GROUP BY session_id
ORDER BY session_id DESC
LIMIT 10;
```

### **Sender Analysis**

```sql
-- Most common senders and their typical classification
SELECT
    from_email,
    COUNT(*) as email_count,
    MODE() WITHIN GROUP (ORDER BY email_type) as typical_type,
    MODE() WITHIN GROUP (ORDER BY importance) as typical_importance,
    ROUND(AVG(entity_extracted) * 100, 1) as entity_extraction_rate
FROM email_threads
GROUP BY from_email
HAVING COUNT(*) >= 3
ORDER BY email_count DESC
LIMIT 20;
```

### **Validation Report**

```sql
-- Check digest coverage validation
SELECT
    session_id,
    COUNT(*) as total,
    SUM(in_featured) as featured,
    SUM(in_orphaned) as orphaned,
    SUM(in_noise) as noise,
    COUNT(*) - (SUM(in_featured) + SUM(in_orphaned) + SUM(in_noise)) as unaccounted
FROM email_threads
GROUP BY session_id
ORDER BY session_id DESC;
```

## Tips

1. **Pretty output**: Use `.mode column` and `.headers on` in sqlite3
2. **Export to CSV**: `.mode csv` then `.output results.csv`
3. **Save queries**: Store common queries as views
4. **JSON fields**: Use `json_extract()` for domains/entity_details
5. **Date filtering**: Use `WHERE timestamp > '2025-10-01'`

## Example Session

```bash
$ sqlite3 -column -header data/mailq_tracking.db

sqlite> .mode column
sqlite> .headers on

sqlite> SELECT COUNT(*) as total_threads FROM email_threads;
total_threads
-------------
150

sqlite> SELECT session_id, COUNT(*) FROM email_threads GROUP BY session_id;
session_id       COUNT(*)
---------------  --------
20251028_071622  50
20251028_091234  45
20251028_143521  55

sqlite> .mode csv
sqlite> .output latest_session.csv
sqlite> SELECT * FROM email_threads WHERE session_id = '20251028_143521';
sqlite> .output stdout
sqlite> .quit
```

## Useful Views

Create views for common queries:

```sql
-- View: Latest session summary
CREATE VIEW latest_session AS
SELECT * FROM email_threads
WHERE session_id = (SELECT MAX(session_id) FROM email_threads);

-- View: Importance summary
CREATE VIEW importance_stats AS
SELECT
    session_id,
    importance,
    COUNT(*) as count
FROM email_threads
GROUP BY session_id, importance;

-- View: Entity extraction issues
CREATE VIEW entity_failures AS
SELECT *
FROM email_threads
WHERE importance != 'routine'
    AND entity_extracted = 0;
```

Then query them simply:

```sql
SELECT * FROM latest_session WHERE in_featured = 1;
SELECT * FROM entity_failures;
```
