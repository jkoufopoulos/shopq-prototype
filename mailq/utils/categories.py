"""Default email categories for new users"""

from __future__ import annotations

DEFAULT_CATEGORIES = [
    {
        "name": "Events",
        "description": ("Calendar invites, meeting notifications, RSVPs, event announcements"),
        "color": "#4CAF50",
    },
    {
        "name": "Finance",
        "description": (
            "Banking statements, investment updates, financial reports, account notifications"
        ),
        "color": "#2196F3",
    },
    {
        "name": "Newsletters",
        "description": (
            "Content subscriptions, industry updates, educational content, regular digests"
        ),
        "color": "#9C27B0",
    },
    {
        "name": "Notifications",
        "description": (
            "System alerts, automated messages, service updates, platform notifications"
        ),
        "color": "#FF9800",
    },
    {
        "name": "Personal",
        "description": (
            "Direct personal communications, individual correspondence, personal services"
        ),
        "color": "#E91E63",
    },
    {
        "name": "Professional",
        "description": (
            "Work-related communications, colleague emails, project discussions, "
            "career opportunities"
        ),
        "color": "#607D8B",
    },
    {
        "name": "Promotions",
        "description": ("Marketing emails, sales, discounts, advertisements, promotional offers"),
        "color": "#FF5722",
    },
    {
        "name": "Receipts",
        "description": (
            "Purchase confirmations, transaction records, payment receipts, order summaries"
        ),
        "color": "#009688",
    },
    {
        "name": "Uncategorized",
        "description": "Emails that don't clearly fit other categories",
        "color": "#9E9E9E",
    },
]
