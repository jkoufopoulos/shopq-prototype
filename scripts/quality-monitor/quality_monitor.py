#!/usr/bin/env python3
"""
ShopQ Quality Monitor Daemon

Continuously monitors classification quality and reports issues.

Usage:
    python quality_monitor.py                    # Run in foreground
    python quality_monitor.py --daemon           # Run as daemon
    python quality_monitor.py --analyze-now      # One-time analysis
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path for mailq imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Path helpers
SCRIPT_DIR = Path(__file__).parent
STATE_DB = SCRIPT_DIR / "quality_monitor.db"
LOG_FILE = SCRIPT_DIR / "quality_monitor.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Import digest format analyzer

# Import GCS storage client
try:
    from shopq.storage.cloud import get_storage_client

    GCS_AVAILABLE = True
except ImportError:
    logger.warning("GCS storage not available, falling back to HTTP API")
    GCS_AVAILABLE = False

# Configuration
API_URL = os.getenv("SHOPQ_API_URL", "https://shopq-api-488078904670.us-central1.run.app")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = "jkoufopoulos/mailq-prototype"  # Update with your repo

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
MIN_SESSIONS_FOR_ANALYSIS = int(os.getenv("MIN_SESSIONS_FOR_ANALYSIS", "1"))
MIN_EMAILS_FOR_ANALYSIS = int(os.getenv("MIN_EMAILS_FOR_ANALYSIS", "25"))
ANALYSIS_WINDOW_HOURS = int(os.getenv("ANALYSIS_WINDOW_HOURS", "48"))

# Budget controls (simple daily limit)
MAX_LLM_CALLS_PER_DAY = int(os.getenv("MAX_LLM_CALLS_PER_DAY", "100"))  # ~$1.50/day max


class QualityMonitor:
    """Monitors ShopQ classification quality and reports issues"""

    def __init__(self):
        self.init_state_db()

    def init_state_db(self):
        """Initialize state tracking database"""
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyzed_sessions (
                session_id TEXT PRIMARY KEY,
                analyzed_at TEXT NOT NULL,
                num_threads INTEGER,
                num_issues INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'classification',
                pattern TEXT NOT NULL,
                evidence TEXT,
                root_cause TEXT,
                suggested_fix TEXT,
                github_issue_url TEXT,
                resolved BOOLEAN DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage_tracking (
                date TEXT PRIMARY KEY,
                classification_calls INTEGER DEFAULT 0,
                digest_calls INTEGER DEFAULT 0,
                total_calls INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

    def check_llm_budget(self) -> bool:
        """Check if we're within daily LLM call budget"""
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()

        today = datetime.utcnow().date().isoformat()
        cursor.execute("SELECT total_calls FROM llm_usage_tracking WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.close()

        today_calls = row[0] if row else 0

        if today_calls >= MAX_LLM_CALLS_PER_DAY:
            logger.warning(
                f"Daily LLM budget exceeded: {today_calls}/{MAX_LLM_CALLS_PER_DAY} calls used"
            )
            return False

        return True

    def track_llm_call(self, call_type: str):
        """Track LLM API call for budget monitoring"""
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()

        today = datetime.utcnow().date().isoformat()

        cursor.execute(
            """
            INSERT INTO llm_usage_tracking (date, classification_calls, digest_calls, total_calls)
            VALUES (?, 0, 0, 0)
            ON CONFLICT(date) DO UPDATE SET
                classification_calls = classification_calls
                    + CASE WHEN ? = 'classification' THEN 1 ELSE 0 END,
                digest_calls = digest_calls
                    + CASE WHEN ? = 'digest' THEN 1 ELSE 0 END,
                total_calls = total_calls + 1
        """,
            (today, call_type, call_type),
        )

        conn.commit()
        conn.close()

    def get_new_sessions(self) -> list[dict]:
        """Fetch sessions that haven't been analyzed yet"""
        try:
            # Get all sessions from GCS (primary source)
            if GCS_AVAILABLE:
                all_sessions = self._get_sessions_from_gcs()
            else:
                # Fallback to API
                url = f"{API_URL}/api/tracking/sessions"
                with urllib.request.urlopen(url, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    all_sessions = data.get("sessions", [])

            # Check which have been analyzed
            conn = sqlite3.connect(STATE_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT session_id FROM analyzed_sessions")
            analyzed = {row[0] for row in cursor.fetchall()}
            conn.close()

            # Return unanalyzed sessions
            return [s for s in all_sessions if s["session_id"] not in analyzed]

        except Exception as e:
            logger.error(f"Failed to fetch sessions: {e}")
            return []

    def _get_sessions_from_gcs(self) -> list[dict]:
        """List all sessions available in GCS"""
        try:
            storage_client = get_storage_client()
            bucket = storage_client.bucket

            # List all .db files in sessions/ prefix
            blobs = list(bucket.list_blobs(prefix="sessions/"))

            sessions = []
            for blob in blobs:
                if blob.name.endswith(".db"):
                    # Extract session_id from filename: sessions/20251108_030835.db
                    session_id = blob.name.replace("sessions/", "").replace(".db", "")
                    sessions.append(
                        {
                            "session_id": session_id,
                            "created_at": blob.time_created.isoformat()
                            if blob.time_created
                            else None,
                        }
                    )

            logger.info(f"Found {len(sessions)} sessions in GCS")
            return sessions

        except Exception as e:
            logger.error(f"Failed to list sessions from GCS: {e}")
            return []

    def get_total_emails_in_sessions(self, sessions: list[dict]) -> int:
        """Calculate total number of emails across sessions"""
        total = 0
        for session in sessions:
            # Try to get thread count from summary
            if isinstance(session, dict):
                summary = session.get("summary", {})
                if isinstance(summary, dict):
                    total += summary.get("total_threads", 0)
        return total

    def fetch_session_details(self, session_ids: list[str]) -> list[dict]:
        """Fetch detailed data for multiple sessions"""
        # Try GCS first, fall back to HTTP API
        if GCS_AVAILABLE:
            return self.fetch_sessions_from_gcs(session_ids)
        return self.fetch_sessions_from_api(session_ids)

    def fetch_sessions_from_gcs(self, session_ids: list[str]) -> list[dict]:
        """Fetch session data from GCS (primary method)"""
        sessions_data = []
        storage_client = get_storage_client()

        for session_id in session_ids:
            try:
                # Download SQLite database from GCS
                db_path = storage_client.download_session_db(session_id)
                if not db_path:
                    logger.warning(f"Session {session_id} not found in GCS")
                    continue

                # Download digest HTML from GCS
                digest_html = storage_client.download_digest_html(session_id)

                # Read tracking data from SQLite
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Get all threads for this session
                cursor.execute(
                    """
                    SELECT * FROM email_threads WHERE session_id = ?
                """,
                    (session_id,),
                )
                threads_data = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                threads = [dict(zip(columns, row, strict=False)) for row in threads_data]

                conn.close()

                # Clean up temp file
                os.unlink(db_path)

                # Build session data structure matching API format
                session_data = {
                    "session_id": session_id,
                    "threads": threads,
                    "summary": {
                        "total_threads": len(threads),
                        "session_id": session_id,
                        "digest_html": digest_html,
                    },
                }

                sessions_data.append(session_data)
                logger.info(f"Loaded session {session_id} from GCS ({len(threads)} threads)")

            except Exception as e:
                logger.error(f"Failed to fetch session {session_id} from GCS: {e}")

        return sessions_data

    def fetch_sessions_from_api(self, session_ids: list[str]) -> list[dict]:
        """Fetch session data from HTTP API (fallback method)"""
        sessions_data = []

        for session_id in session_ids:
            try:
                url = f"{API_URL}/api/tracking/session/{session_id}"
                with urllib.request.urlopen(url, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    sessions_data.append(data)
            except Exception as e:
                logger.error(f"Failed to fetch session {session_id}: {e}")

        return sessions_data

    def analyze_with_claude(self, sessions_data: list[dict]) -> list[dict]:
        """
        Analyze sessions with Claude API

        Returns list of issues:
        [
            {
                "severity": "high|medium|low",
                "pattern": "Description",
                "evidence": "Stats/examples",
                "root_cause": "Why",
                "suggested_fix": "How to fix"
            }
        ]
        """
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set, skipping analysis")
            return []

        # Check daily budget
        if not self.check_llm_budget():
            logger.warning("Daily LLM budget limit reached, skipping classification analysis")
            return []

        # Build analysis prompt
        prompt = self._build_analysis_prompt(sessions_data)

        try:
            # Call Claude API
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0, max_retries=2)

            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            response_text = message.content[0].text

            # Extract JSON (handle markdown code blocks)
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_text = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_text = response_text.strip()

            result = json.loads(json_text)
            issues = result.get("issues", [])

            # Track successful API call
            self.track_llm_call("classification")

            return issues

        except anthropic.APITimeoutError:
            logger.error("Claude API timeout (120s) - analysis taking too long")
            return []
        except anthropic.RateLimitError:
            logger.error("Claude API rate limit exceeded - wait before retrying")
            return []
        except anthropic.AuthenticationError:
            logger.error("Claude API authentication failed - check ANTHROPIC_API_KEY")
            return []
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {type(e).__name__}")
            return []
        except Exception as e:
            logger.error(f"Claude API analysis failed: {type(e).__name__}: {str(e)[:100]}")
            return []

    def _build_analysis_prompt(self, sessions_data: list[dict]) -> str:
        """Build analysis prompt for Claude"""

        # Aggregate stats
        total_threads = sum(s.get("summary", {}).get("total_threads", 0) for s in sessions_data)
        total_critical = sum(
            s.get("summary", {}).get("importance", {}).get("critical", 0) for s in sessions_data
        )
        total_time_sensitive = sum(
            s.get("summary", {}).get("importance", {}).get("time_sensitive", 0)
            for s in sessions_data
        )
        total_routine = sum(
            s.get("summary", {}).get("importance", {}).get("routine", 0) for s in sessions_data
        )
        total_entities = sum(
            s.get("summary", {}).get("entities_extracted", 0) for s in sessions_data
        )
        total_verifier = sum(s.get("summary", {}).get("verified_count", 0) for s in sessions_data)

        # Collect examples
        all_threads = []
        for session in sessions_data:
            all_threads.extend(session.get("threads", []))

        # Sample interesting cases
        critical_examples = [t for t in all_threads if t.get("importance") == "critical"][:10]
        time_sensitive_examples = [
            t for t in all_threads if t.get("importance") == "time_sensitive"
        ][:10]
        routine_examples = [t for t in all_threads if t.get("importance") == "routine"][:10]

        return f"""You are a quality analyst for ShopQ, an AI-powered email classification system.

Analyze the following classification data from the last {len(sessions_data)}
digest sessions and identify systematic issues.

## Overall Statistics
- Total emails processed: {total_threads}
- Critical: {total_critical} ({total_critical / total_threads * 100:.1f}%)
- Time-sensitive: {total_time_sensitive} ({total_time_sensitive / total_threads * 100:.1f}%)
- Routine: {total_routine} ({total_routine / total_threads * 100:.1f}%)
- Entities extracted: {total_entities}/{total_threads} ({total_entities / total_threads * 100:.1f}%)
- Verifier triggered: {total_verifier}/{total_threads} ({total_verifier / total_threads * 100:.1f}%)

## Sample Classifications

### Critical Emails ({len(critical_examples)} samples):
{json.dumps(critical_examples, indent=2)}

### Time-Sensitive Emails ({len(time_sensitive_examples)} samples):
{json.dumps(time_sensitive_examples, indent=2)}

### Routine Emails ({len(routine_examples)} samples):
{json.dumps(routine_examples, indent=2)}

## Your Task

Identify systematic issues with the classification system. Look for:

1. **Misclassification patterns** - Are certain types of emails consistently miscategorized?
2. **Over/under-triggering** - Is critical/time-sensitive being over/under-used?
3. **Rule quality** - Are the pattern-matching rules too broad or too narrow?
4. **Edge cases** - What types of emails are falling through the cracks?
5. **Prompt weaknesses** - Does the LLM classification need improvement?
6. **Entity extraction gaps** - Are important entities being missed?

Return ONLY valid JSON in this format:

    {{
      "issues": [
        {{
          "severity": "high|medium|low",
          "pattern": "Brief description of the pattern "
                     "(e.g., 'Newsletters marked as critical')",
          "evidence": "Specific stats or examples "
                      "(e.g., '3/10 newsletters marked critical: X, Y, Z')",
          "root_cause": "Why this is happening "
                        "(e.g., 'Pattern matches statement is ready but doesn't check sender')",
          "suggested_fix": "Concrete fix "
                           "(e.g., 'Add sender whitelist check for financial institutions')"
        }}
      ]
    }}

Focus on actionable issues that occur in >10% of a category. Ignore one-off edge cases.

Return ONLY the JSON, no other text.
"""

    def create_github_issue(self, issue: dict) -> str | None:
        """Create GitHub issue for a quality problem"""
        if not GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not set, skipping issue creation")
            return None

        try:
            # Build issue body
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}
            emoji = severity_emoji.get(issue["severity"], "⚪")

            title = f"{emoji} [Quality] {issue['pattern']}"

            body = f"""## Issue Pattern
{issue["pattern"]}

## Evidence
{issue["evidence"]}

## Root Cause
{issue["root_cause"]}

## Suggested Fix
{issue["suggested_fix"]}

---
*Auto-generated by Quality Monitor*
*Severity: {issue["severity"]}*
"""

            # Create issue via GitHub API
            url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
            data = json.dumps(
                {
                    "title": title,
                    "body": body,
                    "labels": ["quality", f"severity-{issue['severity']}", "auto-generated"],
                }
            ).encode()

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode())
                issue_url = result.get("html_url")
                logger.info(f"Created GitHub issue: {issue_url}")
                return issue_url

        except Exception as e:
            logger.error(f"Failed to create GitHub issue: {e}")
            return None

    def store_issues(self, issues: list[dict], session_ids: list[str]):
        """Store issues in local database"""
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()

        for issue in issues:
            # Create GitHub issue for high/medium severity
            github_url = None
            if issue["severity"] in ["high", "medium"]:
                github_url = self.create_github_issue(issue)

            # Store in DB (handle both old issues without category and new issues with category)
            category = issue.get("category", "classification")
            cursor.execute(
                """
                INSERT INTO quality_issues (
                    created_at, severity, category, pattern, evidence,
                    root_cause, suggested_fix, github_issue_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    now,
                    issue["severity"],
                    category,
                    issue["pattern"],
                    issue["evidence"],
                    issue["root_cause"],
                    issue["suggested_fix"],
                    github_url,
                ),
            )

        # Mark sessions as analyzed
        for session_id in session_ids:
            cursor.execute(
                """
                INSERT INTO analyzed_sessions (session_id, analyzed_at, num_threads, num_issues)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, now, 0, len(issues)),
            )

        conn.commit()
        conn.close()

    def analyze_digest_format_with_llm(self, digest_html: str) -> list[dict]:
        """
        Use Claude LLM to analyze digest format against ideal structure

        Args:
            digest_html: The actual digest HTML content

        Returns:
            List of format issues detected by LLM
        """
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set, skipping LLM digest analysis")
            return []

        # Check daily budget
        if not self.check_llm_budget():
            logger.warning("Daily LLM budget limit reached, skipping digest analysis")
            return []

        # Validate digest size to prevent cost explosions
        MAX_DIGEST_SIZE = 100_000  # 100KB max
        digest_size = len(digest_html.encode("utf-8"))
        if digest_size > MAX_DIGEST_SIZE:
            logger.error(
                "Digest too large: %s bytes (max %s). Skipping LLM analysis.",
                digest_size,
                MAX_DIGEST_SIZE,
            )
            return []

        # Load prompt template
        prompt_file = SCRIPT_DIR / "prompts" / "digest_format_analysis.txt"
        if not prompt_file.exists():
            logger.error(f"Prompt template not found: {prompt_file}")
            return []

        try:
            # Read prompt template
            with open(prompt_file) as f:
                prompt_template = f.read()

            # Substitute actual digest into prompt
            prompt = prompt_template.replace("{actual_digest}", digest_html)

            # Call Claude API
            import anthropic

            client = anthropic.Anthropic(
                api_key=ANTHROPIC_API_KEY,
                timeout=120.0,  # 2 minute timeout for large digests
                max_retries=2,
            )

            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            response_text = message.content[0].text

            # Extract JSON (handle markdown code blocks)
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_text = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_text = response_text.strip()

            # Parse JSON array with validation
            try:
                issues = json.loads(json_text)
            except json.JSONDecodeError as e:
                logger.error(f"LLM returned invalid JSON: {str(e)[:100]}")
                logger.debug(f"Response preview: {response_text[:200]}")
                return []

            # Ensure it's a list
            if isinstance(issues, dict) and "issues" in issues:
                issues = issues["issues"]
            elif not isinstance(issues, list):
                logger.error(f"Unexpected LLM response format: {type(issues)}")
                return []

            # Validate each issue has required fields
            validated_issues = []
            required_fields = ["severity", "pattern", "evidence", "root_cause", "suggested_fix"]
            for i, issue in enumerate(issues):
                if not isinstance(issue, dict):
                    logger.warning(f"Issue {i} is not a dict, skipping")
                    continue

                # Check required fields
                missing = [f for f in required_fields if f not in issue or not issue[f]]
                if missing:
                    logger.warning("Issue %s missing fields: %s, skipping", i, missing)
                    continue

                # Validate severity
                if issue["severity"] not in ["high", "medium", "low"]:
                    logger.warning(
                        "Issue %s has invalid severity: %s, defaulting to 'medium'",
                        i,
                        issue["severity"],
                    )
                    issue["severity"] = "medium"

                validated_issues.append(issue)

            if len(validated_issues) < len(issues):
                logger.warning("Filtered %s invalid issues", len(issues) - len(validated_issues))

            # Track successful API call
            self.track_llm_call("digest")

            logger.info("LLM digest analysis found %s valid issues", len(validated_issues))
            return validated_issues

        except anthropic.APITimeoutError:
            logger.error("Claude API timeout (120s) - digest may be too large or API slow")
            return []
        except anthropic.RateLimitError:
            logger.error("Claude API rate limit exceeded - wait before retrying")
            return []
        except anthropic.AuthenticationError:
            logger.error("Claude API authentication failed - check ANTHROPIC_API_KEY")
            return []
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {type(e).__name__}")
            return []
        except Exception as e:
            logger.error(f"LLM digest format analysis failed: {type(e).__name__}: {str(e)[:100]}")
            return []

    def get_digest_html_from_files(self, session_id: str) -> str | None:
        """
        Fallback: Read digest HTML from quality_logs directory

        This is a temporary solution until digest HTML is stored in tracking DB
        """
        # Try to find digest HTML file in quality_logs
        quality_logs_dir = SCRIPT_DIR.parent.parent / "quality_logs"
        if not quality_logs_dir.exists():
            return None

        # Look for files matching session_id pattern
        pattern = f"actual_digest_{session_id}*.html"
        matching_files = list(quality_logs_dir.glob(pattern))

        if matching_files:
            logger.info(f"Found digest HTML file: {matching_files[0].name}")
            return matching_files[0].read_text()

        return None

    def analyze_digest_format(self, sessions_data: list[dict]) -> list[dict]:
        """
        Analyze digest format/structure issues using both pattern-based and LLM analysis

        Returns list of format issues in same structure as classification issues
        """
        all_format_issues = []

        for session in sessions_data:
            session_id = session.get("session_id", "unknown")

            # Get digest HTML from session data (if available)
            summary = session.get("summary", {})
            digest_html = summary.get("digest_html")

            # Fallback: try to read from quality_logs directory
            if not digest_html:
                logger.info(f"No digest_html in session {session_id}, checking quality_logs...")
                digest_html = self.get_digest_html_from_files(session_id)

            if not digest_html:
                logger.debug(
                    f"No digest HTML available for session {session_id}, skipping format analysis"
                )
                continue

            # Get input emails for context
            session.get("threads", [])

            try:
                # Use LLM-based analysis for comprehensive digest evaluation
                logger.info(f"Running LLM digest analysis for session {session_id}")
                llm_issues = self.analyze_digest_format_with_llm(digest_html)

                # Add session context to issues
                for issue in llm_issues:
                    issue["session_id"] = session_id
                    # Ensure category is set
                    if "category" not in issue:
                        issue["category"] = "digest_format"

                all_format_issues.extend(llm_issues)

                logger.info(f"Found {len(llm_issues)} format issues in session {session_id}")

            except Exception as e:
                logger.error(f"Digest format analysis failed for session {session_id}: {e}")

        return all_format_issues

    def analyze_now(self, force=False):
        """Run one-time analysis of recent sessions

        Args:
            force: If True, skip volume checks and analyze available sessions

        Triggers when:
        1. At least MIN_SESSIONS_FOR_ANALYSIS new sessions exist, OR
        2. At least MIN_EMAILS_FOR_ANALYSIS emails have been processed across sessions
        """
        logger.info("Running quality analysis...")

        # Get new sessions
        new_sessions = self.get_new_sessions()

        if not force:
            if len(new_sessions) < MIN_SESSIONS_FOR_ANALYSIS:
                logger.info(
                    "Only %s new sessions (need %s), skipping",
                    len(new_sessions),
                    MIN_SESSIONS_FOR_ANALYSIS,
                )
                return

            # Check total email volume across sessions
            total_emails = self.get_total_emails_in_sessions(new_sessions)

            if total_emails < MIN_EMAILS_FOR_ANALYSIS:
                logger.info(
                    "Only %s emails across %s sessions (need %s), skipping",
                    total_emails,
                    len(new_sessions),
                    MIN_EMAILS_FOR_ANALYSIS,
                )
                logger.info("Waiting for more email volume to accumulate...")
                return
        else:
            logger.info(
                "FORCE MODE: Analyzing all %s new sessions regardless of volume",
                len(new_sessions),
            )

        logger.info("Analyzing %s new sessions...", len(new_sessions))

        # Fetch details
        session_ids = [s["session_id"] for s in new_sessions]
        sessions_data = self.fetch_session_details(session_ids)

        if not sessions_data:
            logger.warning("No session data fetched")
            return

        # Calculate actual email count from fetched data
        actual_total = sum(s.get("summary", {}).get("total_threads", 0) for s in sessions_data)
        logger.info("Fetched %s emails from %s sessions", actual_total, len(sessions_data))

        # Analyze classification with Claude
        classification_issues = self.analyze_with_claude(sessions_data)

        # Analyze digest format
        logger.info("Analyzing digest format...")
        format_issues = self.analyze_digest_format(sessions_data)

        # Combine all issues
        all_issues = classification_issues + format_issues

        logger.info(
            "Found %s classification issues + %s format issues = %s total",
            len(classification_issues),
            len(format_issues),
            len(all_issues),
        )

        if not all_issues:
            logger.info("No issues found")
            self.store_issues([], session_ids)
            return

        # Report
        logger.info("Quality issues breakdown:")
        logger.info("  Classification: %s issues", len(classification_issues))
        logger.info("  Format: %s issues", len(format_issues))
        for issue in all_issues:
            logger.info(f"  [{issue['severity'].upper()}] {issue['pattern']}")

        # Store and create GitHub issues
        self.store_issues(all_issues, session_ids)

        logger.info("Analysis complete")

    def analyze_specific_session(self, session_id: str):
        """Analyze a specific session (triggered by webhook)

        Args:
            session_id: Session identifier to analyze
        """
        logger.info("Analyzing specific session: %s", session_id)

        # Check if already analyzed
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id FROM analyzed_sessions WHERE session_id = ?", (session_id,)
        )
        if cursor.fetchone():
            logger.info("Session %s already analyzed, skipping", session_id)
            conn.close()
            return
        conn.close()

        # Fetch session data from GCS
        sessions_data = self.fetch_session_details([session_id])

        if not sessions_data:
            logger.warning("No data found for session %s", session_id)
            return

        # Analyze classification with Claude
        logger.info("Analyzing classifications...")
        classification_issues = self.analyze_with_claude(sessions_data)

        # Analyze digest format
        logger.info("Analyzing digest format...")
        format_issues = self.analyze_digest_format(sessions_data)

        # Combine all issues
        all_issues = classification_issues + format_issues

        logger.info(
            "Found %s total issues (%s classification + %s format)",
            len(all_issues),
            len(classification_issues),
            len(format_issues),
        )

        if not all_issues:
            logger.info("No issues found")
            self.store_issues([], [session_id])
            return

        # Store and create GitHub issues
        self.store_issues(all_issues, [session_id])

        logger.info(f"Analysis complete for session {session_id}")

    def run_daemon(self):
        """Run as continuous daemon"""
        logger.info("Starting Quality Monitor daemon...")
        logger.info(f"Check interval: {CHECK_INTERVAL_MINUTES} minutes")
        logger.info(f"Minimum sessions for analysis: {MIN_SESSIONS_FOR_ANALYSIS}")

        while True:
            try:
                self.analyze_now()
            except Exception as e:
                logger.error(f"Analysis failed: {e}", exc_info=True)

            # Sleep until next check
            logger.info(f"Sleeping for {CHECK_INTERVAL_MINUTES} minutes...")
            time.sleep(CHECK_INTERVAL_MINUTES * 60)


def main():
    parser = argparse.ArgumentParser(description="ShopQ Quality Monitor")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--analyze-now", action="store_true", help="Run one-time analysis")
    parser.add_argument(
        "--force", action="store_true", help="Skip volume checks, analyze all new sessions"
    )
    parser.add_argument(
        "--session-id", type=str, help="Analyze specific session ID (with --analyze-now)"
    )
    args = parser.parse_args()

    monitor = QualityMonitor()

    if args.analyze_now:
        if args.session_id:
            # Analyze specific session from webhook trigger
            monitor.analyze_specific_session(args.session_id)
        else:
            # Analyze all new sessions
            monitor.analyze_now(force=args.force)
    elif args.daemon:
        monitor.run_daemon()
    else:
        # Default: run as daemon
        monitor.run_daemon()


if __name__ == "__main__":
    main()
