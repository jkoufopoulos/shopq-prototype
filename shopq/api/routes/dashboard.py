"""

from __future__ import annotations

Dashboard HTML rendering for feedback visualization
"""

import html
import json
from datetime import datetime


def render_dashboard(
    stats: dict, patterns: list[dict], recent: list[dict], top_senders: list[dict]
) -> str:
    """Render feedback dashboard HTML"""

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ShopQ Feedback Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            {_get_dashboard_css()}
        </style>
    </head>
    <body>
        <h1>📊 ShopQ Feedback Dashboard</h1>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{stats["total_corrections"]}</div>
                <div class="stat-label">Total Corrections</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats["high_confidence_patterns"]}</div>
                <div class="stat-label">High-Confidence Patterns</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(patterns)}</div>
                <div class="stat-label">Ready for Allowlist</div>
            </div>
        </div>

        <div class="section">
            <h2>🔥 Top Corrected Senders</h2>
            {_render_top_senders(top_senders)}
        </div>

        <div class="section">
            <h2>✅ Ready for Allowlist (≥3 corrections)</h2>
            {_render_patterns(patterns)}
        </div>

        <div class="section">
            <h2>📝 Recent Corrections</h2>
            {_render_recent_corrections(recent)}
        </div>

        <div class="footer">
            Last updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC
            <br>
            <a href="/api/feedback/stats">View Stats JSON</a> |
            <a href="/api/debug/last-batch">View Last Batch</a>
        </div>
    </body>
    </html>
    """


def _get_dashboard_css() -> str:
    """Dashboard CSS styles"""
    return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 40px auto;
            padding: 0 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #4CAF50;
        }
        .stat-label {
            color: #666;
            margin-top: 5px;
        }
        .section {
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section h2 {
            margin-top: 0;
            color: #333;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }
        .correction-item {
            padding: 15px;
            border-left: 4px solid #4CAF50;
            margin: 10px 0;
            background: #f9f9f9;
        }
        .sender {
            font-weight: bold;
            color: #2196F3;
        }
        .predicted {
            color: #f44336;
        }
        .actual {
            color: #4CAF50;
        }
        .count {
            float: right;
            background: #4CAF50;
            color: white;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.9em;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #f5f5f5;
            font-weight: 600;
        }
        .ready-badge {
            background: #4CAF50;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }
        .footer {
            text-align: center;
            margin: 40px 0;
            color: #999;
        }
        .footer a {
            color: #4CAF50;
            text-decoration: none;
        }
        .footer a:hover {
            text-decoration: underline;
        }
    """


def _render_top_senders(senders: list[dict]) -> str:
    """Render top corrected senders

    All user-provided fields are HTML-escaped to prevent XSS attacks.
    """
    if not senders:
        return "<p>No corrections yet.</p>"

    result = ""
    for sender in senders:
        # Escape user-provided fields to prevent XSS
        from_field = html.escape(sender["from_field"])
        predicted = html.escape(sender["most_common_predicted"])
        actual = html.escape(sender["most_common_actual"])

        result += f"""
        <div class="correction-item">
            <span class="count">{sender["count"]}x</span>
            <div class="sender">{from_field}</div>
            <div style="margin-top: 5px;">
                <span class="predicted">Predicted: {predicted}</span>
                →
                <span class="actual">Corrected to: {actual}</span>
            </div>
        </div>
        """
    return result


def _render_patterns(patterns: list[dict]) -> str:
    """Render high-confidence patterns ready for allowlist

    All user-provided fields are HTML-escaped to prevent XSS attacks.
    """
    if not patterns:
        return "<p>No high-confidence patterns yet. Need 3+ corrections per sender.</p>"

    result = (
        "<table><thead><tr><th>Sender</th><th>Classification</th>"
        "<th>Support</th><th>Action</th></tr></thead><tbody>"
    )

    for p in patterns:
        classification = p["classification"]
        # Escape user-provided fields to prevent XSS
        sender = html.escape(p["sender"])
        type_str = html.escape(classification.get("type", "unknown"))
        domains = ", ".join(html.escape(d) for d in classification.get("domains", []))

        result += f"""
        <tr>
            <td><strong>{sender}</strong></td>
            <td>Type: {type_str}<br>Domains: {domains or "none"}</td>
            <td>{p["support_count"]}x</td>
            <td><span class="ready-badge">Ready</span></td>
        </tr>
        """

    result += "</tbody></table>"
    return result


def _render_recent_corrections(corrections: list[dict]) -> str:
    """Render recent corrections table

    All user-provided fields are HTML-escaped to prevent XSS attacks.
    """
    if not corrections:
        return "<p>No corrections yet.</p>"

    result = """
    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>From</th>
                <th>Subject</th>
                <th>Predicted</th>
                <th>Actual</th>
            </tr>
        </thead>
        <tbody>
    """

    for c in corrections:
        # Escape user-provided fields to prevent XSS
        predicted = ", ".join(html.escape(lbl) for lbl in json.loads(c["predicted_labels"]))
        actual = ", ".join(html.escape(lbl) for lbl in json.loads(c["actual_labels"]))
        from_field = html.escape(c["from_field"])
        subject = html.escape(c["subject"])
        timestamp = datetime.fromisoformat(c["timestamp"]).strftime("%m/%d %H:%M")

        result += f"""
        <tr>
            <td>{timestamp}</td>
            <td style="max-width: 200px; overflow: hidden;
                text-overflow: ellipsis;">{from_field}</td>
            <td style="max-width: 300px; overflow: hidden;
                text-overflow: ellipsis;">{subject}</td>
            <td><span class="predicted">{predicted}</span></td>
            <td><span class="actual">{actual}</span></td>
        </tr>
        """

    result += "</tbody></table>"
    return result
