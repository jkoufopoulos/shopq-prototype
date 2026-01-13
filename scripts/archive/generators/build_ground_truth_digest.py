#!/usr/bin/env python3
"""
Build a digest HTML from the GDS ground truth classification table.

This script parses the classification table and generates a digest HTML
using the Ground Truth Section assignments and GDS Type information.
"""

from dataclasses import dataclass


@dataclass
class EmailData:
    """Email data from the classification table."""

    email_id: str
    received: str
    subject: str
    gds_type: str
    gds_importance: str
    has_temporal: bool
    shopq_section: str
    ground_truth_section: str
    match: bool


def parse_classification_table() -> list[EmailData]:
    """Parse the classification table from the provided data."""
    # Data extracted from the table
    emails = [
        # worth_knowing section
        EmailData(
            "email_001",
            "Nov 7 10:37pm",
            "Invitation: Dinner Justin <> Adam @ F...",
            "event",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_003",
            "Nov 6 2:27pm",
            "[Action Required] Update Google Meet ...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_005",
            "Nov 7 11:23pm",
            "Updated invitation: Show Justin <> Ad...",
            "event",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_006",
            "Nov 6 4:59pm",
            'Delivered: "Slippers"',
            "notification",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_011",
            "Nov 2 6:07am",
            "Your Saturday evening order with Uber...",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_015",
            "Nov 9 6:32am",
            "Your weekly receipt for 11/02 - 11/08",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_016",
            "Nov 3 11:59pm",
            'Ordered: "Reed Diffuser Set" and 2 mo...',
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_023",
            "Nov 5 2:04pm",
            "Thanks for your payment!",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_024",
            "Nov 8 11:36am",
            "[Personal] Your Saturday morning orde...",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_026",
            "Nov 9 3:53pm",
            'Ordered: "Quick Size Paper Towels"',
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_028",
            "Nov 7 12:04pm",
            "Fwd: Own the patient journey @ Nouris...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_031",
            "Nov 3 11:44pm",
            "Apple Services: $21.19 USD",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_032",
            "Nov 3 9:22am",
            "[Personal] Your Sunday evening order ...",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_035",
            "Nov 5 3:19pm",
            'Shipped: "Slippers"',
            "notification",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_038",
            "Nov 8 6:52am",
            "[Personal] Your Friday evening order ...",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_039",
            "Nov 8 6:03pm",
            "Your Venmo Standard transfer has been...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_041",
            "Nov 3 9:29pm",
            "Your Whole Foods Market order has bee...",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_042",
            "Nov 9 10:25am",
            "Your monthly account statement is her...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_043",
            "Nov 4 1:49pm",
            'Shipped: "Reed Diffuser Set" and 2 mo...',
            "notification",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_045",
            "Nov 2 2:35am",
            "[Personal] Your Saturday afternoon or...",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_046",
            "Nov 7 7:16am",
            "[Personal] Your Thursday evening orde...",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_048",
            "Nov 5 12:43am",
            'Ordered: "Slippers"',
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_054",
            "Nov 5 10:29am",
            "[billing] Heroku Invoice for October ...",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_059",
            "Nov 9 3:35pm",
            "An update on your YouTube TV credit",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_060",
            "Nov 7 5:03pm",
            "Disclosure About Your Retirement Plan",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_061",
            "Nov 2 2:25pm",
            "Your Whole Foods Market order has bee...",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_062",
            "Nov 9 3:07am",
            "Ride Receipt",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_063",
            "Nov 5 2:29pm",
            'Delivered: "Reed Diffuser Set" and 2 ...',
            "notification",
            "routine",
            True,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_065",
            "Nov 2 11:54am",
            "Your October statement summary is ready",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_066",
            "Nov 5 12:53am",
            "Justin, your bill was deleted from Ex...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_068",
            "Nov 5 3:48pm",
            "Action Item from Apoorva Avutu at One...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        EmailData(
            "email_070",
            "Nov 7 6:52pm",
            "Your app is ready. Now put your name ...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "worth_knowing",
            True,
        ),
        # coming_up section
        EmailData(
            "email_008",
            "Nov 6 2:28pm",
            "Your AutoPay is set for Nov 12, 2025",
            "receipt",
            "routine",
            True,
            "worth_knowing",
            "coming_up",
            False,
        ),
        # everything_else section
        EmailData(
            "email_002",
            "Nov 5 8:42pm",
            "Lovable Update - Shopify integration,...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_009",
            "Nov 4 8:45am",
            "Part 2 of how to get the most out of ...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_010",
            "Nov 3 8:37am",
            "'My Friend Is an Asshole!'",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_017",
            "Nov 5 9:47am",
            "$500K sales gig + AI BFFs with bodies...",
            "promotion",
            "routine",
            False,
            "everything_else",
            "everything_else",
            True,
        ),
        EmailData(
            "email_018",
            "Nov 6 12:00pm",
            "Substack on Film: Stella Tsantekidou",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_019",
            "Nov 5 9:05am",
            "I Tried Every AI Productivity and Cod...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_020",
            "Nov 9 9:05am",
            "7 Counterintuitive Product Lessons fr...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_021",
            "Nov 5 9:12am",
            "Technically Monthly (November 2025)",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_025",
            "Nov 9 8:31am",
            '"Sell the alpha, not the feature": Th...',
            "promotion",
            "routine",
            False,
            "everything_else",
            "everything_else",
            True,
        ),
        EmailData(
            "email_027",
            "Nov 8 11:01am",
            "INVESCO FUNDS Important Information",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_029",
            "Nov 7 1:07pm",
            "Frothiness and the Future (This Week ...",
            "promotion",
            "routine",
            False,
            "everything_else",
            "everything_else",
            True,
        ),
        EmailData(
            "email_030",
            "Nov 8 6:04pm",
            "The Definitive Report on the AI PM Ma...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_033",
            "Nov 6 7:42am",
            "4 repeat items added. Reserve a time ...",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_034",
            "Nov 2 9:05am",
            "Full Tutorial: Vibe Code a Real SaaS ...",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_036",
            "Nov 3 12:02pm",
            "Last chance to register for our free ...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_037",
            "Nov 7 12:31pm",
            "Taste. Vibe. Celebrate. — Bites & Bey...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_044",
            "Nov 8 4:30am",
            "Important investment information for ...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_047",
            "Nov 7 11:59am",
            "[PIFF] Survey for Nov 10",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_050",
            "Nov 7 12:02pm",
            "5 grooming tips that get you noticed",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_051",
            "Nov 4 5:26pm",
            "Important Update to Play: Now you can...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_053",
            "Nov 8 9:03am",
            "\"We're discussing the best way to sto...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_064",
            "Nov 2 8:31am",
            "The woman behind Canva shares how she...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        EmailData(
            "email_069",
            "Nov 3 11:02am",
            'This week on How I AI: "Vibe analysis...',
            "notification",
            "routine",
            False,
            "worth_knowing",
            "everything_else",
            False,
        ),
        # skip section
        EmailData(
            "email_004",
            "Nov 2 6:20pm",
            "Notification: Downtown Dharma Weekly ...",
            "notification",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_007",
            "Nov 9 12:50pm",
            "Notification: Call with mom @ Sun Nov...",
            "notification",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_012",
            "Nov 9 2:54pm",
            "Invitation: PS @ Sun Nov 9, 2025 7pm ...",
            "event",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_013",
            "Nov 9 6:20pm",
            "Notification: Downtown Dharma Weekly ...",
            "notification",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_014",
            "Nov 9 3:47pm",
            "Updated invitation: PS @ Sun Nov 9, 2...",
            "event",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_022",
            "Nov 3 6:19pm",
            "Notification: Jonathan Foust Monday E...",
            "notification",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_040",
            "Nov 5 2:04pm",
            "Updated invitation with note: J & V C...",
            "event",
            "routine",
            True,
            "coming_up",
            "skip",
            False,
        ),
        EmailData(
            "email_049",
            "Nov 9 9:50am",
            "Notification: Jonathan Sunday AM medi...",
            "notification",
            "routine",
            True,
            "worth_knowing",
            "skip",
            False,
        ),
        EmailData(
            "email_052",
            "Nov 2 12:50pm",
            "Notification: Call with mom @ Sun Nov...",
            "notification",
            "routine",
            True,
            "skip",
            "skip",
            True,
        ),
        EmailData(
            "email_055",
            "Nov 5 11:36am",
            "Reminder: Braun Men's Aesthetic Event...",
            "notification",
            "routine",
            False,
            "worth_knowing",
            "skip",
            False,
        ),
        EmailData(
            "email_056",
            "Nov 5 11:49am",
            "Notification: Appointment with Susan ...",
            "notification",
            "routine",
            True,
            "worth_knowing",
            "skip",
            False,
        ),
        EmailData(
            "email_057",
            "Nov 6 3:07am",
            "[GitHub] Sudo email verification code",
            "notification",
            "critical",
            False,
            "critical",
            "skip",
            False,
        ),
        EmailData(
            "email_058",
            "Nov 3 8:37pm",
            "Your Whole Foods Market order is out ...",
            "receipt",
            "routine",
            False,
            "worth_knowing",
            "skip",
            False,
        ),
        EmailData(
            "email_067",
            "Nov 2 9:50am",
            "Notification: Jonathan Sunday AM medi...",
            "notification",
            "routine",
            True,
            "worth_knowing",
            "skip",
            False,
        ),
    ]

    return emails


def group_emails_by_section(emails: list[EmailData]) -> dict[str, list[EmailData]]:
    """Group emails by their ground truth section."""
    sections = {
        "critical": [],
        "today": [],
        "coming_up": [],
        "worth_knowing": [],
        "everything_else": [],
        "skip": [],
    }

    for email in emails:
        section = email.ground_truth_section
        if section in sections:
            sections[section].append(email)

    return sections


def count_by_type(emails: list[EmailData]) -> dict[str, int]:
    """Count emails by GDS type."""
    counts = {}
    for email in emails:
        email_type = email.gds_type
        counts[email_type] = counts.get(email_type, 0) + 1
    return counts


def generate_digest_html(emails: list[EmailData]) -> str:
    """Generate digest HTML based on ground truth sections."""
    sections = group_emails_by_section(emails)

    # Calculate statistics
    total_emails = len(emails)
    critical_count = len(sections["critical"])
    today_count = len(sections["today"])
    coming_up_count = len(sections["coming_up"])
    worth_knowing_count = len(sections["worth_knowing"])
    everything_else_count = len(sections["everything_else"])
    skip_count = len(sections["skip"])

    # Count by type for everything_else
    everything_else_types = count_by_type(sections["everything_else"])

    # Generate HTML
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 600px;
            margin: 20px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }

        .context-card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .header {
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 20px;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 12px;
        }

        .content {
            font-size: 15px;
            line-height: 1.6;
            color: #444;
        }

        .content a {
            color: #0066cc;
            text-decoration: none;
        }

        .content a:hover {
            text-decoration: underline;
        }

        .footer {
            margin-top: 20px;
            padding-top: 16px;
            border-top: 1px solid #f0f0f0;
            text-align: center;
        }

        .footer a {
            color: #666;
            text-decoration: none;
            font-size: 14px;
        }

        .footer a:hover {
            color: #333;
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="context-card">
        <div class="header">
            Your Inbox — Sunday, November 10 at 6:20 PM EST
        </div>

        <div class="content">"""

    # Opening line
    html += (
        f"Hey! Based on the ground truth classifications, you have {critical_count} critical alerts"
    )
    if coming_up_count > 0:
        html += f" and {coming_up_count} upcoming items"
    html += ".<br><br>"

    # Critical section
    if critical_count > 0:
        html += f'<p style="font-weight: 600; margin-top: 16px; margin-bottom: 8px;">🚨 CRITICAL ({critical_count} emails):</p>'
        for i, email in enumerate(sections["critical"], 1):
            html += f'<p style="margin: 0 0 4px 20px;">• {email.subject} <a href="https://mail.google.com/mail/u/0/#inbox/{email.email_id}" target="_blank" style="color: #1a73e8; text-decoration: none;">({i})</a></p>'

    # Today section
    html += f'<p style="font-weight: 600; margin-top: 16px; margin-bottom: 8px;">📦 TODAY ({today_count} emails):</p>'
    if today_count > 0:
        for i, email in enumerate(sections["today"], 1):
            html += f'<p style="margin: 0 0 4px 20px;">• {email.subject} <a href="https://mail.google.com/mail/u/0/#inbox/{email.email_id}" target="_blank" style="color: #1a73e8; text-decoration: none;">({i})</a></p>'
    else:
        html += '<p style="margin: 0 0 8px 20px; color: #666; font-style: italic;">Nothing due today</p>'

    # Coming up section
    html += f'<p style="font-weight: 600; margin-top: 16px; margin-bottom: 8px;">📅 COMING UP ({coming_up_count} emails):</p>'
    if coming_up_count > 0:
        for i, email in enumerate(sections["coming_up"], 1):
            html += f'<p style="margin: 0 0 4px 20px;">• {email.subject} <a href="https://mail.google.com/mail/u/0/#inbox/{email.email_id}" target="_blank" style="color: #1a73e8; text-decoration: none;">({i})</a></p>'
    else:
        html += '<p style="margin: 0 0 8px 20px; color: #666; font-style: italic;">Nothing coming up</p>'

    # Worth knowing section
    html += f'<p style="font-weight: 600; margin-top: 16px; margin-bottom: 8px;">💼 WORTH KNOWING ({worth_knowing_count} emails):</p>'
    if worth_knowing_count > 0:
        # List all emails individually
        for i, email in enumerate(sections["worth_knowing"], 1):
            html += f'<p style="margin: 0 0 4px 20px;">• {email.subject} <a href="https://mail.google.com/mail/u/0/#inbox/{email.email_id}" target="_blank" style="color: #1a73e8; text-decoration: none;">({i})</a></p>'
    else:
        html += '<p style="margin: 0 0 8px 20px; color: #666; font-style: italic;">Nothing else to note</p>'

    html += '<p style="margin-top: 16px;">Have a great day!</p>\n\n'
    html += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Everything else footer
    if everything_else_count > 0 or skip_count > 0:
        total_hidden = everything_else_count + skip_count
        html += f"Otherwise, there are {total_hidden} low-priority emails in your inbox: "

        parts = []
        if everything_else_count > 0:
            ee_by_type = count_by_type(sections["everything_else"])
            for email_type, count in sorted(ee_by_type.items()):
                label = "promos" if email_type == "promotion" else f"{email_type}s"
                parts.append(
                    f'<a href="https://mail.google.com/mail/u/0/#search/label%3AShopQ-{email_type.title()}+in%3Aanywhere+-in%3Atrash+-in%3Aspam">{count} {label}</a>'
                )

        if skip_count > 0:
            parts.append(
                f'<a href="https://mail.google.com/mail/u/0/#search/label%3AShopQ-Skip+in%3Aanywhere+-in%3Atrash+-in%3Aspam">{skip_count} skipped</a>'
            )

        html += ", ".join(parts) + "."

    html += """</div>

        <div class="footer">
            <a href="https://mail.google.com/mail/u/0/#search/is%3Aunread+newer_than%3A1d">→ Anything still important?</a>
        </div>
    </div>
</body>
</html>
"""

    return html


def main():
    """Main function to generate the digest."""
    print("Building digest from GDS ground truth classifications...")

    # Parse the classification table
    emails = parse_classification_table()
    print(f"Parsed {len(emails)} emails from classification table")

    # Group by section
    sections = group_emails_by_section(emails)
    print("\nEmail counts by ground truth section:")
    for section, email_list in sections.items():
        print(f"  {section}: {len(email_list)}")

    # Generate HTML
    html = generate_digest_html(emails)

    # Write to file
    output_path = (
        "/Users/justinkoufopoulos/Projects/mailq-prototype/reports/ground_truth_digest_t1.html"
    )
    with open(output_path, "w") as f:
        f.write(html)

    print(f"\n✓ Digest generated: {output_path}")


if __name__ == "__main__":
    main()
