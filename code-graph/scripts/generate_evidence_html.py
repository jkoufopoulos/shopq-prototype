#!/usr/bin/env python3
"""Generate evidence heat-map HTML from markdown data"""

import re
import subprocess
import json
import html
from pathlib import Path
from datetime import datetime
try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = None
    ValidationError = Exception

from diagram_types import GitCommit, TodoItem, ComponentDetails, ActivityRow, QualityMetrics

PROJECT_ROOT = Path(__file__).parent.parent.parent
VISUALS_DIR = PROJECT_ROOT / "code-graph" / "visuals"
HTML_DIR = VISUALS_DIR / "html"


# ============================================================================
# Pydantic Models for Validation (optional - degrades gracefully if not available)
# ============================================================================


if PYDANTIC_AVAILABLE:
    class GitCommitModel(BaseModel):
        """Pydantic model for validating git commit data."""
        hash: str
        when: str
        message: str

        class Config:
            str_strip_whitespace = True  # Auto-strip whitespace
else:
    # Fallback: simple validation without Pydantic
    class GitCommitModel:
        """Fallback validation when Pydantic not available."""
        def __init__(self, hash: str, when: str, message: str):
            if not hash or not when or not message:
                raise ValueError("Invalid commit data")
            self.hash = hash.strip()
            self.when = when.strip()
            self.message = message.strip()

def parse_markdown_table(md_content: str) -> list[ActivityRow]:
    """Extract table data from markdown"""
    rows = []
    in_table = False

    for line in md_content.split('\n'):
        if '| Layer |' in line:
            in_table = True
            continue
        if in_table and line.startswith('|---'):
            continue
        if in_table and line.startswith('|'):
            parts = [p.strip() for p in line.split('|')[1:-1]]  # Remove empty first/last
            if len(parts) == 5 and not parts[0].startswith('Layer'):
                rows.append({
                    'layer': parts[0],
                    'component': parts[1].replace('`', ''),
                    'commits': parts[2],
                    'todos': parts[3],
                    'activity': parts[4]
                })
        elif in_table and not line.strip().startswith('|'):
            break

    return rows

def extract_insights(md_content: str) -> list[str]:
    """Extract migration insights from markdown (legacy - now replaced by generate_dynamic_insights)"""
    insights = []
    in_section = False

    for line in md_content.split('\n'):
        if '## 🔄 Recent Migration & Initiative Insights' in line:
            in_section = True
            continue
        if in_section and line.startswith('- **'):
            insights.append(line[2:])  # Remove "- " prefix
        elif in_section and line.startswith('##'):
            break

    return insights

def generate_dynamic_insights(component_data: dict) -> list[dict]:
    """
    Generate time-aware insights from actual git data.

    Returns list of insight dicts with:
    - title: Initiative name
    - status: 'active' | 'recent' | 'completed'
    - commits: Number of commits
    - timeframe: Human-readable timeframe
    - files: List of affected files
    - freshness_hours: Hours since last commit (for sorting)
    """
    from datetime import datetime, timedelta
    from collections import defaultdict

    # Group components by topic/initiative based on file patterns
    initiatives = defaultdict(lambda: {'files': [], 'commits': [], 'most_recent_hours': 99999})

    # Define initiative patterns
    patterns = {
        'Database & Persistence': ['database', 'email_tracker', 'retention', 'config/database'],
        'Digest Generation': ['digest', 'context_digest', 'hybrid', 'card_renderer', 'categorizer'],
        'Classification & Rules': ['classifier', 'rules', 'mapper', 'importance', 'guardrails', 'bridge'],
        'Chrome Extension': ['background.js', 'content', 'popup', 'options.js', 'cache.js'],
        'API & Auth': ['api.py', 'auth.py', 'rate_limit', 'middleware'],
        'Feedback & Learning': ['feedback', 'learning', 'entity_extractor', 'deduplicator']
    }

    def parse_time_to_hours(time_str: str) -> float:
        """Convert '2 hours ago' to hours as float"""
        match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago', time_str)
        if not match:
            return 99999

        num = int(match.group(1))
        unit = match.group(2)

        hours_map = {
            'second': 1/3600, 'minute': 1/60, 'hour': 1,
            'day': 24, 'week': 24*7, 'month': 24*30, 'year': 24*365
        }
        return num * hours_map[unit]

    # Analyze each component
    for component, data in component_data.items():
        if not data or 'commits' not in data or not data['commits']:
            continue

        # Find which initiative this belongs to
        matched_initiative = None
        for initiative_name, keywords in patterns.items():
            if any(keyword in component.lower() for keyword in keywords):
                matched_initiative = initiative_name
                break

        if not matched_initiative:
            matched_initiative = 'Other Changes'

        # Get commit info
        commit_count = len(data['commits'])
        most_recent = data['commits'][0] if data['commits'] else None

        if most_recent and 'when' in most_recent:
            hours_ago = parse_time_to_hours(most_recent['when'])

            initiatives[matched_initiative]['files'].append(component)
            initiatives[matched_initiative]['commits'].extend(data['commits'])
            initiatives[matched_initiative]['most_recent_hours'] = min(
                initiatives[matched_initiative]['most_recent_hours'],
                hours_ago
            )

    # Convert to insights with status
    insights = []
    for initiative_name, data in initiatives.items():
        if not data['files']:
            continue

        hours = data['most_recent_hours']
        commit_count = len(data['commits'])

        # Determine status and timeframe
        if hours < 24:
            status = 'active'
            status_emoji = '🟢'
            timeframe = 'Active now (last 24h)'
        elif hours < 24 * 7:
            status = 'recent'
            status_emoji = '🟡'
            timeframe = 'Recent (last week)'
        elif hours < 24 * 30:
            status = 'recent'
            status_emoji = '🟡'
            timeframe = 'Recent (last month)'
        else:
            status = 'completed'
            status_emoji = '⚪'
            timeframe = 'Completed (>1 month ago)'

        insights.append({
            'title': initiative_name,
            'status': status,
            'status_emoji': status_emoji,
            'commits': commit_count,
            'timeframe': timeframe,
            'files': data['files'][:3],  # Top 3 files
            'freshness_hours': hours
        })

    # Sort by freshness (most recent first)
    insights.sort(key=lambda x: x['freshness_hours'])

    return insights

def fetch_component_details_from_git_and_disk(component: str) -> ComponentDetails | dict[str, str]:
    """
    Fetch component details by executing git commands and reading files.

    Side Effects:
    - Executes `git log` subprocess (reads git history for component)
    - Reads component file from disk to extract TODOs and imports
    - May timeout after 10 seconds if git operations hang
    - Writes no files (read-only operation)

    Args:
        component: File name (e.g., "api.py", "background.js")

    Returns:
        Dict with keys: path, commits (list), todos (list), imports (list)
        Returns dict with "error" key if component name is invalid or file not found

    Security:
        Validates component name format to prevent path traversal attacks
    """

    # SECURITY: Validate component name to prevent path traversal
    if not re.match(r'^[a-zA-Z0-9_.-]+\.(js|py)$', component):
        return {"error": "Invalid component name format"}

    if '/' in component or '\\' in component:
        return {"error": "Component name cannot contain path separators"}

    # Determine file paths
    if component.endswith('.js'):
        file_paths = list(PROJECT_ROOT.glob(f"extension/**/{component}"))
    elif component.endswith('.py'):
        file_paths = list(PROJECT_ROOT.glob(f"shopq/**/{component}"))
    else:
        return {"error": "Unknown file type"}

    if not file_paths:
        return {"error": "File not found"}

    file_path = file_paths[0]  # Take first match

    # SECURITY: Verify resolved path is within PROJECT_ROOT
    try:
        file_path = file_path.resolve()
        project_root_resolved = PROJECT_ROOT.resolve()
        if not str(file_path).startswith(str(project_root_resolved)):
            return {"error": "Path traversal attempt detected"}
    except Exception:
        return {"error": "Invalid file path"}

    relative_path = file_path.relative_to(PROJECT_ROOT)

    details = {
        "path": str(relative_path),
        "commits": [],
        "todos": [],
        "imports": []
    }

    # Get recent commits (last 5)
    try:
        result = subprocess.run(
            ["git", "log", "-5", "--pretty=format:%h|%ar|%s", "--", str(relative_path)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=10
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                if '|' in line:
                    parts = line.split('|', 2)
                    if len(parts) != 3:
                        # Invalid format - log and skip
                        continue

                    hash_val, when, msg = parts

                    # VALIDATION: Validate git output
                    try:
                        commit = GitCommitModel(
                            hash=hash_val,
                            when=when,
                            message=msg
                        )
                        # SECURITY: Escape HTML to prevent XSS from malicious commit messages
                        details["commits"].append({
                            "hash": html.escape(commit.hash),
                            "when": html.escape(commit.when),
                            "message": html.escape(commit.message)
                        })
                    except (ValidationError, ValueError) as e:
                        # Invalid commit data - skip this line
                        continue
    except subprocess.TimeoutExpired:
        details["commits"] = [{"error": "Git log timed out"}]
    except Exception as e:
        details["commits"] = [{"error": html.escape(str(e))}]

    # Extract TODOs from file
    try:
        if file_path.exists():
            content = file_path.read_text()
            for i, line in enumerate(content.split('\n'), 1):
                if 'TODO' in line or 'FIXME' in line:
                    # SECURITY: Escape HTML to prevent XSS from malicious TODO comments
                    details["todos"].append({
                        "line": i,
                        "text": html.escape(line.strip())
                    })
    except Exception as e:
        details["todos"] = [{"error": html.escape(str(e))}]

    # Extract imports (Python or JS)
    try:
        if file_path.exists():
            content = file_path.read_text()
            if component.endswith('.py'):
                # Python imports
                import_pattern = r'^(?:from|import)\s+([a-zA-Z0-9_.]+)'
                for match in re.finditer(import_pattern, content, re.MULTILINE):
                    module = match.group(1)
                    if not module.startswith('shopq.'):
                        # SECURITY: Escape module names (unlikely to contain HTML, but defense in depth)
                        details["imports"].append(html.escape(module))
            elif component.endswith('.js'):
                # JavaScript imports
                import_pattern = r'(?:from\s+[\'"](.+?)[\'"]|require\([\'"](.+?)[\'"]\))'
                for match in re.finditer(import_pattern, content):
                    module = match.group(1) or match.group(2)
                    if module and not module.startswith('.'):
                        details["imports"].append(html.escape(module))
    except Exception as e:
        details["imports"] = [{"error": html.escape(str(e))}]

    return details

def get_all_component_details(rows: list[dict]) -> dict:
    """
    Extract details for all components by calling git and reading files.

    Side Effects:
    - Executes git subprocess for each component in rows
    - Reads component files from disk
    - May take several seconds depending on number of components

    Args:
        rows: List of dicts with 'component' key

    Returns:
        Dict mapping component name to component details
    """
    component_data = {}
    for row in rows:
        component = row['component']
        component_data[component] = fetch_component_details_from_git_and_disk(component)
    return component_data

def get_quality_metrics() -> QualityMetrics:
    """
    Extract quality metrics by executing pytest, reading logs, and scanning for TODOs.

    Side Effects:
    - Executes `pytest --collect-only` subprocess
    - Reads quality_monitor.log file from disk
    - Executes `grep` subprocess to find CRITICAL/FIXME/XXX comments
    - May timeout after 10 seconds per subprocess
    - Writes no files (read-only operation)

    Returns:
        Dict with keys: test_failures, recent_errors, components_with_issues
    """
    metrics = {
        "test_failures": [],
        "recent_errors": [],
        "components_with_issues": set()
    }

    # Check for recent test failures
    try:
        result = subprocess.run(
            ["pytest", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=10
        )
        if result.returncode != 0:
            metrics["test_failures"].append({
                "message": "Test collection failed",
                "details": result.stderr[:200] if result.stderr else "Unknown error"
            })
    except subprocess.TimeoutExpired:
        metrics["test_failures"].append({"message": "Test collection timed out"})
    except Exception as e:
        metrics["test_failures"].append({"message": f"Error running tests: {str(e)}"})

    # Parse quality monitor log for recent errors
    try:
        log_path = PROJECT_ROOT / "scripts" / "quality-monitor" / "quality_monitor.log"
        if log_path.exists():
            log_content = log_path.read_text()
            error_lines = []
            for line in log_content.split('\n')[-100:]:  # Last 100 lines
                if 'ERROR' in line or 'CRITICAL' in line:
                    error_lines.append(line)

            # Extract unique error messages
            unique_errors = {}
            for line in error_lines:
                # Extract error message
                match = re.search(r'\[ERROR\]\s+(.+)', line)
                if match:
                    error_msg = match.group(1)
                    if error_msg not in unique_errors:
                        unique_errors[error_msg] = 1
                    else:
                        unique_errors[error_msg] += 1

            # Add top 5 errors
            for error_msg, count in sorted(unique_errors.items(), key=lambda x: x[1], reverse=True)[:5]:
                metrics["recent_errors"].append({
                    "message": error_msg,
                    "count": count
                })

                # Try to extract component from error
                for component in ['api.py', 'classifier', 'digest', 'memory', 'rules']:
                    if component in error_msg.lower():
                        metrics["components_with_issues"].add(component)
    except Exception as e:
        metrics["recent_errors"].append({"message": f"Error reading logs: {str(e)}", "count": 1})

    # Check for critical TODOs/FIXMEs in hot components
    try:
        shopq_path = PROJECT_ROOT / "mailq"
        extension_path = PROJECT_ROOT / "extension"

        # Validate paths exist
        if not shopq_path.is_dir() or not extension_path.is_dir():
            metrics["recent_errors"].append({
                "message": "Required directories not found for TODO scan",
                "count": 1
            })
        else:
            # Use -E for extended regex (clearer than \|)
            result = subprocess.run(
                ["grep", "-r", "-n", "-E", "--include=*.py", "--include=*.js",
                 "(CRITICAL|FIXME|XXX)",
                 str(shopq_path), str(extension_path)],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=10
            )
            if result.returncode == 0:
                critical_lines = result.stdout.strip().split('\n')[:10]  # First 10
                for line in critical_lines:
                    if ':' in line:
                        file_path = line.split(':')[0]
                        component_name = Path(file_path).name
                        metrics["components_with_issues"].add(component_name)
    except subprocess.TimeoutExpired:
        metrics["recent_errors"].append({
            "message": "TODO scan timed out after 10 seconds",
            "count": 1
        })
    except FileNotFoundError:
        metrics["recent_errors"].append({
            "message": "grep command not found - install grep to enable TODO scanning",
            "count": 1
        })
    except KeyboardInterrupt:
        raise
    except Exception as e:
        metrics["recent_errors"].append({
            "message": f"Unexpected error in TODO scan: {type(e).__name__}",
            "count": 1
        })

    metrics["components_with_issues"] = list(metrics["components_with_issues"])
    return metrics

def generate_html(rows: list[dict], insights: list[str], timestamp: str, component_data: dict, quality_metrics: dict) -> str:
    """Generate complete HTML page"""

    # Add quality indicator to rows
    components_with_issues = set(quality_metrics.get("components_with_issues", []))

    def build_row(r):
        has_issue = r["component"] in components_with_issues
        bg_style = " background: #2c2c2e; border-left: 3px solid #ff6b6b;" if has_issue else ""
        warning_icon = '<span style="color: #ff6b6b; margin-left: 8px;" title="Has quality issues">⚠️</span>' if has_issue else ""
        return f'                    <tr onclick="showDetails(\'{r["component"]}\')" style="cursor: pointer;{bg_style}"><td>{r["layer"]}</td><td><code>{r["component"]}</code>{warning_icon}</td><td>{r["commits"]}</td><td>{r["todos"]}</td><td>{r["activity"]}</td></tr>'

    table_rows = '\n'.join([build_row(r) for r in rows])

    # Get latest commits across all components
    all_commits = []
    for component, data in component_data.items():
        if data and 'commits' in data and data['commits']:
            for commit in data['commits'][:1]:  # Just the most recent per file
                if not commit.get('error'):
                    all_commits.append({
                        'component': component,
                        'hash': commit['hash'],
                        'when': commit['when'],
                        'message': commit['message']
                    })

    # Sort by recency (parse "X hours ago" to get most recent)
    def parse_time_for_sort(when_str):
        import re
        match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago', when_str)
        if not match:
            return 999999
        num = int(match.group(1))
        unit = match.group(2)
        hours_map = {'second': 1/3600, 'minute': 1/60, 'hour': 1, 'day': 24, 'week': 24*7, 'month': 24*30, 'year': 24*365}
        return num * hours_map[unit]

    all_commits.sort(key=lambda c: parse_time_for_sort(c['when']))
    latest_commits = all_commits[:5]  # Top 5 most recent

    # Generate dynamic insights
    dynamic_insights = generate_dynamic_insights(component_data)

    # Build insight items with status indicators
    insight_items = '\n'.join([
        f'''                    <li style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>{insight['status_emoji']} {insight['title']}</strong>
                            <span style="color: #a1a1a6; font-size: 13px; margin-left: 8px;">({insight['commits']} commits)</span>
                            <div style="font-size: 13px; color: #86868b; margin-top: 4px;">
                                {insight['timeframe']} • Files: {', '.join(insight['files'])}
                            </div>
                        </div>
                    </li>'''
        for insight in dynamic_insights
    ])

    # Build quality metrics section
    quality_html = ""
    if quality_metrics.get("recent_errors"):
        error_items = '\n'.join([
            f'                    <li><strong>{err["count"]}x</strong> {err["message"][:100]}...</li>'
            for err in quality_metrics["recent_errors"][:3]
        ])
        quality_html = f'''
            <div class="quality-section" style="background: #1c1c1e; padding: 32px; border-radius: 18px; border: 1px solid #d32f2f; margin-bottom: 32px;">
                <h3 style="margin-bottom: 16px; color: #ff6b6b; font-size: 24px; font-weight: 600;">⚠️ Recent Quality Issues</h3>
                <ul style="list-style: none;">
{error_items}
                </ul>
                <p style="margin-top: 16px; font-size: 14px; color: #a1a1a6;"><strong>{len(quality_metrics.get("components_with_issues", []))}</strong> components flagged with potential issues (highlighted in table)</p>
            </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 Architecture Activity Heat-Map</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
            background: #000000;
            min-height: 100vh;
            padding: 60px 40px;
            color: #f5f5f7;
        }}

        .container {{
            max-width: 1280px;
            margin: 0 auto;
        }}

        .header {{
            text-align: center;
            margin-bottom: 64px;
        }}

        .header h1 {{
            font-size: 56px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 12px;
            letter-spacing: -0.02em;
        }}

        .header p {{
            font-size: 21px;
            color: #a1a1a6;
            font-weight: 400;
            line-height: 1.4;
        }}

        .controls {{
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 24px;
        }}

        .btn {{
            background: #1c1c1e;
            color: #f5f5f7;
            border: 1px solid #2c2c2e;
            padding: 12px 24px;
            border-radius: 12px;
            text-decoration: none;
            font-size: 15px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .btn:hover {{
            background: #2c2c2e;
            border-color: #3a3a3c;
            transform: translateY(-2px);
        }}

        .content {{
            margin-bottom: 48px;
        }}

        h2 {{
            margin-bottom: 24px;
            color: #ffffff;
            font-size: 32px;
            font-weight: 600;
            letter-spacing: -0.01em;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 48px;
            background: #1c1c1e;
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid #2c2c2e;
        }}

        thead {{
            background: #2c2c2e;
        }}

        th {{
            padding: 16px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
            color: #f5f5f7;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
        }}

        th:hover {{
            background: #3a3a3c;
        }}

        tbody tr {{
            border-bottom: 1px solid #2c2c2e;
            transition: background 0.2s;
        }}

        tbody tr:hover {{
            background: #2c2c2e;
        }}

        tbody tr:last-child {{
            border-bottom: none;
        }}

        td {{
            padding: 16px;
            font-size: 15px;
            color: #f5f5f7;
        }}

        td:first-child {{
            font-size: 20px;
        }}

        td:nth-child(2) code {{
            background: #2c2c2e;
            padding: 4px 8px;
            border-radius: 6px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #f5f5f7;
        }}

        td:nth-child(3), td:nth-child(4) {{
            text-align: center;
            font-weight: 600;
            color: #a1a1a6;
        }}

        td:nth-child(5) {{
            text-align: center;
            font-size: 24px;
        }}

        .insights {{
            background: #1c1c1e;
            padding: 32px;
            border-radius: 18px;
            border: 1px solid #2c2c2e;
            margin-bottom: 32px;
        }}

        .insights h3 {{
            margin-bottom: 16px;
            color: #ffffff;
            font-size: 24px;
            font-weight: 600;
        }}

        .insights ul {{
            list-style: none;
        }}

        .insights li {{
            padding: 12px 0;
            border-bottom: 1px solid #2c2c2e;
            color: #f5f5f7;
        }}

        .insights li:last-child {{
            border-bottom: none;
        }}

        .insights strong {{
            color: #0a84ff;
        }}

        .usage {{
            background: #1c1c1e;
            padding: 32px;
            border-radius: 18px;
            border: 1px solid #2c2c2e;
        }}

        .usage h3 {{
            margin-bottom: 16px;
            color: #ffffff;
            font-size: 24px;
            font-weight: 600;
        }}

        .usage ol {{
            padding-left: 24px;
            color: #f5f5f7;
        }}

        .usage li {{
            margin-bottom: 8px;
        }}

        .footer {{
            background: #1c1c1e;
            padding: 32px;
            text-align: center;
            color: #a1a1a6;
            font-size: 14px;
            border-radius: 18px;
            border: 1px solid #2c2c2e;
            margin-top: 64px;
        }}

        .footer a {{
            color: #0a84ff;
            text-decoration: none;
        }}

        .footer a:hover {{
            text-decoration: underline;
        }}

        .sort-indicator {{
            margin-left: 8px;
            opacity: 0.5;
        }}

        .time-btn {{
            background: transparent;
            border: none;
            color: #a1a1a6;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
        }}

        .time-btn:hover {{
            background: #2c2c2e;
            color: #ffffff;
        }}

        .time-btn.active {{
            background: #0a84ff;
            color: #ffffff;
        }}

        .time-btn.active:hover {{
            background: #0070e0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 Architecture Activity: What's Changing?</h1>

            <div style="background: #1c1c1e; border: 1px solid #2c2c2e; border-radius: 18px; padding: 24px; margin: 32px auto; max-width: 900px;">
                <h3 style="color: #ffffff; font-size: 18px; font-weight: 600; margin-bottom: 16px;">📝 Latest Activity</h3>
                <div style="display: flex; flex-direction: column; gap: 12px;">
                    {''.join([
                        f'''<div style="display: flex; justify-content: space-between; align-items: start; padding: 12px; background: #2c2c2e; border-radius: 12px; border-left: 3px solid #0a84ff;">
                            <div style="flex: 1;">
                                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                    <code style="background: #1c1c1e; padding: 2px 8px; border-radius: 6px; font-size: 12px; color: #0a84ff;">{commit['hash']}</code>
                                    <code style="background: #1c1c1e; padding: 2px 8px; border-radius: 6px; font-size: 12px; color: #a1a1a6;">{commit['component']}</code>
                                </div>
                                <div style="color: #f5f5f7; font-size: 14px;">{commit['message']}</div>
                            </div>
                            <span style="color: #86868b; font-size: 13px; white-space: nowrap; margin-left: 16px;">{commit['when']}</span>
                        </div>'''
                        for commit in latest_commits
                    ])}
                </div>
            </div>

            <div class="controls">
                <a href="index.html" class="btn">← All Diagrams</a>
                <a href="../EVIDENCE_HEATMAP.md" class="btn" target="_blank">📄 View Markdown</a>
            </div>
        </div>

        <div class="content">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <h2 style="margin: 0;">📊 Activity by Component</h2>

                <div style="display: flex; gap: 8px; background: #1c1c1e; padding: 6px; border-radius: 12px; border: 1px solid #2c2c2e;">
                    <button class="time-btn active" onclick="filterByTime('all')" data-time="all">All Time</button>
                    <button class="time-btn" onclick="filterByTime('day')" data-time="day">Last 24h</button>
                    <button class="time-btn" onclick="filterByTime('week')" data-time="week">Last Week</button>
                    <button class="time-btn" onclick="filterByTime('month')" data-time="month">Last Month</button>
                </div>
            </div>

            <table id="activityTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Layer <span class="sort-indicator">↕</span></th>
                        <th onclick="sortTable(1)">Component <span class="sort-indicator">↕</span></th>
                        <th onclick="sortTable(2)">Commits <span class="sort-indicator">↕</span></th>
                        <th onclick="sortTable(3)">TODOs <span class="sort-indicator">↕</span></th>
                        <th onclick="sortTable(4)">Activity <span class="sort-indicator">↕</span></th>
                    </tr>
                </thead>
                <tbody>
{table_rows}
                </tbody>
            </table>

            <div class="insights">
                <h3>🔄 Initiative Activity Tracker</h3>
                <p style="color: #a1a1a6; font-size: 14px; margin-bottom: 16px;">
                    Auto-detected from commit patterns • 🟢 Active (24h) • 🟡 Recent (week/month) • ⚪ Completed (>1 month)
                </p>
                <ul>
{insight_items}
                </ul>
            </div>

{quality_html}

            <div class="usage">
                <h3>💡 How to Use This</h3>
                <ol>
                    <li><strong>Click any row</strong> to see component details (recent commits, TODOs, imports)</li>
                    <li><strong>Click column headers</strong> to sort the table</li>
                    <li><strong>Scan the Activity column</strong> - See where work is concentrated at a glance</li>
                    <li><strong>Group by Layer</strong> - Sort by layer to see architectural patterns</li>
                    <li><strong>Check TODOs</strong> - Non-zero TODOs indicate incomplete work</li>
                    <li><strong>Track week-over-week</strong> - Compare to identify cooling/heating trends</li>
                </ol>
            </div>
        </div>

        <div class="footer">
            <p><strong>Keep this fresh:</strong> Run <code>./code-graph/scripts/quick_regen.sh</code> weekly to track changes</p>
            <p style="margin-top: 8px;">See also: <a href="layer_map.html">Layer Map</a> to understand layer responsibilities</p>
        </div>
    </div>

    <!-- Component Details Modal -->
    <div id="detailsModal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; overflow: auto;">
        <div style="background: #1c1c1e; max-width: 800px; margin: 50px auto; border-radius: 18px; box-shadow: 0 20px 60px rgba(0,0,0,0.5); border: 1px solid #2c2c2e;">
            <div style="background: #2c2c2e; color: #f5f5f7; padding: 24px; border-radius: 18px 18px 0 0; display: flex; justify-content: space-between; align-items: center;">
                <h2 id="modalTitle" style="margin: 0; font-size: 24px; font-weight: 600;">Component Details</h2>
                <button onclick="closeDetails()" style="background: #3a3a3c; color: #f5f5f7; border: 1px solid #48484a; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 18px; transition: all 0.2s;">✕</button>
            </div>
            <div id="modalContent" style="padding: 32px; max-height: 600px; overflow-y: auto; background: #1c1c1e; color: #f5f5f7; border-radius: 0 0 18px 18px;">
                Loading...
            </div>
        </div>
    </div>

    <script>
        const componentData = {json.dumps(component_data)};


        function sortTable(columnIndex) {{
            const table = document.getElementById('activityTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            // Determine sort direction
            const currentSort = tbody.dataset.sortColumn;
            const currentDir = tbody.dataset.sortDir || 'asc';
            const newDir = (currentSort === String(columnIndex) && currentDir === 'asc') ? 'desc' : 'asc';

            rows.sort((a, b) => {{
                let aVal = a.cells[columnIndex].textContent.trim();
                let bVal = b.cells[columnIndex].textContent.trim();

                // Handle numeric columns
                if (columnIndex === 2 || columnIndex === 3) {{
                    aVal = parseInt(aVal);
                    bVal = parseInt(bVal);
                }}

                // Handle activity column (count fire emojis)
                if (columnIndex === 4) {{
                    const countFires = (str) => (str.match(/🔥/g) || []).length;
                    aVal = countFires(aVal);
                    bVal = countFires(bVal);
                }}

                if (aVal < bVal) return newDir === 'asc' ? -1 : 1;
                if (aVal > bVal) return newDir === 'asc' ? 1 : -1;
                return 0;
            }});

            // Clear and re-append rows
            rows.forEach(row => tbody.appendChild(row));

            // Store sort state
            tbody.dataset.sortColumn = columnIndex;
            tbody.dataset.sortDir = newDir;

            // Update sort indicators
            table.querySelectorAll('th .sort-indicator').forEach(el => {{
                el.textContent = '↕';
            }});
            table.querySelectorAll('th')[columnIndex].querySelector('.sort-indicator').textContent =
                newDir === 'asc' ? '↑' : '↓';
        }}

        let currentTimeFilter = 'all';

        function filterByTime(timeFilter) {{
            currentTimeFilter = timeFilter;
            applyFilters();

            // Update button states
            document.querySelectorAll('.time-btn').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.time === timeFilter);
            }});
        }}

        function parseTimeAgo(timeStr) {{
            // Convert "2 hours ago", "3 days ago" etc to hours
            const match = timeStr.match(/(\\d+)\\s+(second|minute|hour|day|week|month|year)s?\\s+ago/);
            if (!match) return 99999; // Unknown time = very old

            const num = parseInt(match[1]);
            const unit = match[2];

            const hoursMap = {{
                'second': 1/3600,
                'minute': 1/60,
                'hour': 1,
                'day': 24,
                'week': 24 * 7,
                'month': 24 * 30,
                'year': 24 * 365
            }};

            return num * hoursMap[unit];
        }}

        function getComponentName(row) {{
            // Extract component name from code tag, ignoring warning icons
            const codeEl = row.cells[1].querySelector('code');
            return codeEl ? codeEl.textContent.trim() : row.cells[1].textContent.trim();
        }}

        function applyFilters() {{
            const table = document.getElementById('activityTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            // Filter by time
            let filteredRows = rows;
            if (currentTimeFilter !== 'all') {{
                const timeLimit = {{
                    'day': 24,
                    'week': 24 * 7,
                    'month': 24 * 30
                }}[currentTimeFilter];

                filteredRows = rows.filter(row => {{
                    const component = getComponentName(row);
                    const data = componentData[component];

                    if (!data || !data.commits || data.commits.length === 0) return false;

                    // Check if most recent commit is within time range
                    const mostRecentCommit = data.commits[0];
                    if (!mostRecentCommit || !mostRecentCommit.when) return false;

                    const hoursAgo = parseTimeAgo(mostRecentCommit.when);
                    return hoursAgo <= timeLimit;
                }});
            }}

            // Hide all rows first
            rows.forEach(row => row.style.display = 'none');

            // Show filtered rows
            filteredRows.forEach(row => row.style.display = '');
        }}

        function showDetails(component) {{
            const data = componentData[component];
            if (!data) {{
                alert('No details available for ' + component);
                return;
            }}

            document.getElementById('modalTitle').textContent = component;

            let html = `<div style="font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;">`;

            // Path
            if (data.path) {{
                html += `<div style="background: #2c2c2e; padding: 12px 16px; border-radius: 12px; margin-bottom: 24px; border: 1px solid #3a3a3c;">
                    <strong style="color: #0a84ff;">📁 Path:</strong> <code style="background: #1c1c1e; padding: 4px 8px; border-radius: 6px; color: #f5f5f7;">${{data.path}}</code>
                </div>`;
            }}

            // Recent Commits
            html += `<h3 style="margin-bottom: 16px; color: #ffffff; font-size: 20px; font-weight: 600;">📝 Recent Commits</h3>`;
            if (data.commits && data.commits.length > 0) {{
                html += `<div style="background: #2c2c2e; border-radius: 12px; padding: 16px; margin-bottom: 24px;">`;
                data.commits.forEach(commit => {{
                    if (commit.error) {{
                        html += `<div style="color: #ff6b6b; padding: 8px 0;">Error: ${{commit.error}}</div>`;
                    }} else {{
                        html += `<div style="border-left: 3px solid #0a84ff; padding: 12px 16px; margin-bottom: 12px; background: #1c1c1e; border-radius: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                                <code style="background: #2c2c2e; padding: 2px 8px; border-radius: 4px; font-size: 12px; color: #f5f5f7;">${{commit.hash}}</code>
                                <span style="color: #a1a1a6; font-size: 13px;">${{commit.when}}</span>
                            </div>
                            <div style="color: #f5f5f7;">${{commit.message}}</div>
                        </div>`;
                    }}
                }});
                html += `</div>`;
            }} else {{
                html += `<p style="color: #a1a1a6; font-style: italic; margin-bottom: 24px;">No recent commits found</p>`;
            }}

            // TODOs
            html += `<h3 style="margin-bottom: 16px; color: #ffffff; font-size: 20px; font-weight: 600;">📌 TODOs & FIXMEs</h3>`;
            if (data.todos && data.todos.length > 0) {{
                html += `<div style="background: #2c2c2e; border-radius: 12px; padding: 16px; margin-bottom: 24px;">`;
                data.todos.forEach(todo => {{
                    if (todo.error) {{
                        html += `<div style="color: #ff6b6b; padding: 8px 0;">Error: ${{todo.error}}</div>`;
                    }} else {{
                        html += `<div style="border-left: 3px solid #ff9f0a; padding: 12px 16px; margin-bottom: 12px; background: #1c1c1e; border-radius: 8px;">
                            <div style="color: #a1a1a6; font-size: 13px; margin-bottom: 4px;">Line ${{todo.line}}</div>
                            <code style="font-size: 13px; color: #f5f5f7;">${{todo.text}}</code>
                        </div>`;
                    }}
                }});
                html += `</div>`;
            }} else {{
                html += `<p style="color: #a1a1a6; font-style: italic; margin-bottom: 24px;">No TODOs found</p>`;
            }}

            // Imports
            html += `<h3 style="margin-bottom: 16px; color: #ffffff; font-size: 20px; font-weight: 600;">📦 External Dependencies</h3>`;
            if (data.imports && data.imports.length > 0) {{
                html += `<div style="background: #2c2c2e; border-radius: 12px; padding: 16px;">`;
                const uniqueImports = [...new Set(data.imports)].sort();
                uniqueImports.forEach(imp => {{
                    html += `<span style="background: #1c1c1e; padding: 6px 12px; border-radius: 8px; display: inline-block; margin: 4px; font-size: 14px; border: 1px solid #3a3a3c; color: #f5f5f7;">${{imp}}</span>`;
                }});
                html += `</div>`;
            }} else {{
                html += `<p style="color: #a1a1a6; font-style: italic;">No external dependencies found</p>`;
            }}

            html += `</div>`;

            document.getElementById('modalContent').innerHTML = html;
            document.getElementById('detailsModal').style.display = 'block';
        }}

        function closeDetails() {{
            document.getElementById('detailsModal').style.display = 'none';
        }}

        // Close modal when clicking outside
        document.getElementById('detailsModal').addEventListener('click', function(e) {{
            if (e.target === this) {{
                closeDetails();
            }}
        }});

        // No initialization needed - show all rows by default
    </script>
</body>
</html>
'''

def generate_and_save_evidence_heatmap() -> Path | None:
    """
    Generate evidence heatmap HTML and save to disk.

    Side Effects:
    - Reads EVIDENCE_HEATMAP.md from code-graph/visuals/
    - Creates code-graph/visuals/html/ directory if it doesn't exist
    - Writes evidence_heatmap.html file (overwrites if exists)
    - Executes git subprocesses to fetch component details
    - Executes pytest and grep subprocesses for quality metrics
    - Reads component files from disk
    - May take 5-10 seconds depending on git history size

    Returns:
        Path to generated HTML file, or None if markdown file not found
    """
    # Read markdown
    md_path = VISUALS_DIR / "EVIDENCE_HEATMAP.md"
    if not md_path.exists():
        print(f"Error: {md_path} not found. Run generate_diagrams.py first.")
        return None

    md_content = md_path.read_text()

    # Extract timestamp
    timestamp_match = re.search(r'Last updated: ([\d\-: ]+)', md_content)
    timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().strftime('%Y-%m-%d %H:%M')

    # Parse data
    rows = parse_markdown_table(md_content)
    insights = extract_insights(md_content)

    # Extract component details
    print("🔍 Extracting component details...")
    component_data = get_all_component_details(rows)

    # Extract quality metrics
    print("🔍 Extracting quality metrics...")
    quality_metrics = get_quality_metrics()

    # Generate HTML
    html = generate_html(rows, insights, timestamp, component_data, quality_metrics)

    # Write
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    html_path = HTML_DIR / "evidence_heatmap.html"
    html_path.write_text(html)

    print(f"✅ Generated {html_path}")
    if quality_metrics.get("recent_errors"):
        print(f"⚠️  Found {len(quality_metrics['recent_errors'])} recent quality issues")
    if quality_metrics.get("components_with_issues"):
        print(f"⚠️  {len(quality_metrics['components_with_issues'])} components flagged with issues")

    return html_path

if __name__ == "__main__":
    generate_and_save_evidence_heatmap()
