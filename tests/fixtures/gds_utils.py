"""Utilities for loading GDS (Ground Data Set) test data."""

from __future__ import annotations

import csv
from pathlib import Path

GDS_DIR = Path(__file__).resolve().parents[2] / "data" / "evals" / "classification"
GDS_CSV = GDS_DIR / "gds-2.0.csv"


def load_messages() -> list[dict]:
    """Load GDS emails from CSV."""
    messages = []
    with GDS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            messages.append(
                {
                    "id": row.get("message_id", ""),
                    "from": row.get("from_email", ""),
                    "subject": row.get("subject", ""),
                    "snippet": row.get("snippet", ""),
                    "body": row.get("body", ""),
                    "type": row.get("email_type", ""),
                    "attention": row.get("attention", ""),
                }
            )
    return messages


def load_labels() -> dict[str, dict[str, str]]:
    """Load expected importance/type labels keyed by message id."""
    labels = {}
    with GDS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            msg_id = row.get("message_id", "")
            if msg_id:
                labels[msg_id] = {
                    "importance": row.get("importance", ""),
                    "type": row.get("email_type", ""),
                }
    return labels
