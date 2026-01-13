# ruff: noqa
"""
Generate CSV with 50 sample emails for temporal digest section review.

Creates a T0 golden dataset where user manually labels which section each email
should be in, considering temporal decay at different timepoints:
- T0: Just received (current time)
- T1: 24 hours after first email
- T2: 168 hours (1 week) after most recent email

This creates test cases for validating temporal decay + categorization logic.
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from shopq.classification.decay import resolve_temporal_importance

from shopq.classification.importance_mapping.guardrails import GuardrailMatcher
from shopq.classification.importance_mapping.mapper import BridgeImportanceMapper
from shopq.classification.pipeline_wrapper import RefactoredPipelineClassifier


def _predict_digest_section(importance: str, email_type: str, category: str) -> str:
    """
    Predict digest section based on importance, type, and category.

    Mapping logic (for T0 - just received):
    - critical → CRITICAL section
    - time_sensitive → COMING UP section (events/appointments 1-7 days)
    - routine + (receipt/confirmation) → WORTH KNOWING section
    - routine + (promotion/newsletter) → EVERYTHING ELSE section
    - everything else → WORTH KNOWING (default)

    Note: This is a simplified prediction for T0. T1/T2 require temporal decay logic
    which needs actual timestamps (not available in static dataset).
    """
    importance = (importance or "").lower()
    email_type = (email_type or "").lower()
    category = (category or "").lower()

    # Critical importance → CRITICAL section
    if importance == "critical":
        return "critical"

    # Time-sensitive importance → COMING UP section
    # (Events, appointments, deadlines 1-7 days out)
    if importance == "time_sensitive":
        return "coming_up"

    # Routine importance → depends on type
    if importance == "routine":
        # Receipts, confirmations → WORTH KNOWING
        if email_type in ["receipt", "confirmation"]:
            return "worth_knowing"

        # Promotions, newsletters → EVERYTHING ELSE
        if email_type in ["promotion", "newsletter", "marketing"]:
            return "everything_else"

        # Social media, surveys → SKIP
        if email_type in ["social", "survey"]:
            return "skip"

        # Default routine → WORTH KNOWING
        return "worth_knowing"

    # Fallback
    return "worth_knowing"


def _predict_section_with_temporal_decay(
    stored_importance: str,
    email_type: str,
    category: str,
    temporal_start: datetime | None,
    temporal_end: datetime | None,
    now: datetime,
    email_id: str = "unknown",
) -> str:
    """
    Predict digest section using temporal decay logic.

    Args:
        stored_importance: Initial importance (critical/time_sensitive/routine)
        email_type: Email type (event, deadline, notification, etc.)
        category: Email category
        temporal_start: Event/deadline start time
        temporal_end: Event end time (None for deadlines)
        now: Current time for temporal calculation
        email_id: Email identifier for error logging

    Returns:
        Predicted digest section: critical, today, coming_up, worth_knowing, everything_else, or skip
    """
    # For emails with temporal fields, use temporal decay
    if temporal_start and email_type in ["event", "deadline", "notification"]:
        try:
            result = resolve_temporal_importance(
                email_type=email_type,
                stored_importance=stored_importance,
                temporal_start=temporal_start,
                temporal_end=temporal_end,
                now=now,
            )

            resolved_importance = result.resolved_importance

            # Check if should be hidden (expired)
            if result.decay_reason == "temporal_expired":
                return "skip"
        except Exception as e:
            print(f"  ⚠️  Temporal decay failed for {email_id}: {type(e).__name__}: {e}")
            # Fallback to stored importance without temporal decay
            resolved_importance = stored_importance
    else:
        # No temporal fields, use stored importance
        resolved_importance = stored_importance

    # Map resolved importance to section (same as T0 logic)
    return _predict_digest_section(resolved_importance, email_type, category)


def main():
    parser = argparse.ArgumentParser(description="Generate temporal testing dataset")
    parser.add_argument(
        "--seed", type=int, default=50, help="Random seed for sampling (default: 50)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path (default: reports/temporal_digest_review_50_emails_seed{SEED}.csv)",
    )
    parser.add_argument(
        "--n-emails", type=int, default=50, help="Number of emails to sample (default: 50)"
    )
    args = parser.parse_args()

    # Load GDS
    gds_path = Path(__file__).parent.parent / "tests" / "golden_set" / "gds-1.0.csv"
    gds = pd.read_csv(gds_path)

    # Sample N random emails for temporal testing
    # NOTE: Using different seeds (50, 51, etc.) for each dataset
    # to avoid overfitting and enable cross-validation
    # These SAME N emails will be evaluated at T0, T1, T2 to test temporal decay
    sample = gds.sample(n=min(args.n_emails, len(gds)), random_state=args.seed)

    # Classify emails
    base_classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)

    results = []

    print(f"🔄 Classifying {args.n_emails} emails for temporal digest review (seed={args.seed})...")
    print()

    # T0/T1/T2 will be calculated per-email based on actual received_date
    # Each email has its own timeline: T0 = when received, T1 = +24h, T2 = +72h

    for idx, (_, email_row) in enumerate(sample.iterrows(), 1):
        # Backend classification
        base_classification = base_classifier.classify(
            subject=email_row["subject"],
            snippet=email_row["snippet"],
            from_field=email_row["from_email"],
        )

        # Apply importance mapping
        email_with_classification = {
            "subject": email_row["subject"],
            "snippet": email_row["snippet"],
            "from": email_row["from_email"],
            **base_classification,
        }

        decision = importance_mapper.map_email(email_with_classification)
        final_importance = decision.importance or "routine"

        # Extract received_date to calculate T0/T1/T2 timepoints
        received_date_str = email_row.get("received_date", "")
        received_timestamp = None

        if pd.notna(received_date_str) and received_date_str != "":
            try:
                received_timestamp = pd.to_datetime(received_date_str, utc=True)
                # Ensure timezone-aware
                if received_timestamp.tzinfo is None:
                    received_timestamp = received_timestamp.replace(tzinfo=UTC)
            except Exception as e:
                print(f"  ⚠️  Invalid received_date for email {idx}: {e}")

        # Calculate T0/T1/T2 based on actual received date (or fallback to "now")
        if received_timestamp:
            t0_time = received_timestamp
        else:
            t0_time = datetime.now(UTC)  # Fallback if no received_date

        t1_time = t0_time + timedelta(hours=24)  # T1: +24 hours from received
        t2_time = t0_time + timedelta(hours=168)  # T2: +168 hours (1 week) from received

        # Extract temporal fields from GDS (if available)
        temporal_start = None
        temporal_end = None

        temporal_start_val = email_row.get("temporal_start")
        temporal_end_val = email_row.get("temporal_end")

        if pd.notna(temporal_start_val) and temporal_start_val != "":
            try:
                parsed = pd.to_datetime(temporal_start_val, utc=True)
                # Ensure timezone-aware (convert naive to UTC if needed)
                if parsed.tzinfo is None:
                    temporal_start = parsed.replace(tzinfo=UTC)
                else:
                    temporal_start = parsed.astimezone(UTC)
            except Exception as e:
                print(f"  ⚠️  Invalid temporal_start for email {idx} '{temporal_start_val}': {e}")

        if pd.notna(temporal_end_val) and temporal_end_val != "":
            try:
                parsed = pd.to_datetime(temporal_end_val, utc=True)
                # Ensure timezone-aware (convert naive to UTC if needed)
                if parsed.tzinfo is None:
                    temporal_end = parsed.replace(tzinfo=UTC)
                else:
                    temporal_end = parsed.astimezone(UTC)
            except Exception as e:
                print(f"  ⚠️  Invalid temporal_end for email {idx} '{temporal_end_val}': {e}")

        # Validate temporal window (end must be after start)
        if temporal_start is not None and temporal_end is not None:
            if temporal_end < temporal_start:
                print(
                    f"  ⚠️  Invalid event window for email {idx}: end ({temporal_end}) before start ({temporal_start})"
                )
                # Treat as invalid temporal data
                temporal_start = None
                temporal_end = None

        # Predict digest section for T0, T1, T2 using temporal decay
        email_type = base_classification.get("type", "")
        category = base_classification.get("category", "")

        # T0: Just received (no temporal decay yet)
        predicted_section_t0 = _predict_digest_section(final_importance, email_type, category)

        # T1: +24 hours (apply temporal decay)
        predicted_section_t1 = _predict_section_with_temporal_decay(
            final_importance,
            email_type,
            category,
            temporal_start,
            temporal_end,
            t1_time,
            email_id=f"email_{idx:03d}",
        )

        # T2: +72 hours (apply temporal decay)
        predicted_section_t2 = _predict_section_with_temporal_decay(
            final_importance,
            email_type,
            category,
            temporal_start,
            temporal_end,
            t2_time,
            email_id=f"email_{idx:03d}",
        )

        # received_date_str already extracted above for T0/T1/T2 calculation

        results.append(
            {
                "email_id": f"email_{idx:03d}",
                "subject": email_row["subject"],
                "from": email_row["from_email"],
                "snippet": email_row["snippet"][:200],  # First 200 chars for context
                "received_date": received_date_str,  # When email was received (for T1/T2 context)
                "predicted_importance": final_importance,
                "predicted_type": base_classification.get("type", ""),
                "predicted_category": base_classification.get("category", ""),
                "predicted_section_t0": predicted_section_t0,  # System's section prediction for T0
                "predicted_section_t1": predicted_section_t1,  # System's section prediction for T1 (+24h)
                "predicted_section_t2": predicted_section_t2,  # System's section prediction for T2 (+72h)
                # T0 Labels (just received)
                "t0_critical": "",  # User marks X if should be in CRITICAL at T0
                "t0_today": "",  # User marks X if should be in TODAY at T0
                "t0_coming_up": "",  # User marks X if should be in COMING UP at T0
                "t0_worth_knowing": "",  # User marks X if should be in WORTH KNOWING at T0
                "t0_everything_else": "",  # User marks X if should be in EVERYTHING ELSE at T0
                "t0_skip": "",  # User marks X if should be skipped at T0
                # T1 Labels (24 hours after first email) - user will fill these separately
                "t1_critical": "",
                "t1_today": "",
                "t1_coming_up": "",
                "t1_worth_knowing": "",
                "t1_everything_else": "",
                "t1_skip": "",
                # T2 Labels (72 hours after most recent email) - user will fill these separately
                "t2_critical": "",
                "t2_today": "",
                "t2_coming_up": "",
                "t2_worth_knowing": "",
                "t2_everything_else": "",
                "t2_skip": "",
                # Metadata
                "temporal_hints": "",  # User notes about temporal aspects (e.g., "event tomorrow", "delivered package")
                "notes": "",  # General notes
            }
        )

    # Save to CSV
    output_df = pd.DataFrame(results)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = (
            Path(__file__).parent.parent
            / "reports"
            / f"temporal_digest_review_50_emails_seed{args.seed}.csv"
        )

    output_df.to_csv(output_path, index=False)

    print(f"✅ Created temporal review CSV with {len(output_df)} emails")
    print(f"📂 Location: {output_path}")
    print()
    print("=" * 80)
    print("INSTRUCTIONS")
    print("=" * 80)
    print()
    print("This CSV is designed for 3-phase temporal testing:")
    print()
    print("PHASE 1: T0 Labeling (just received)")
    print("-" * 80)
    print("Label each email for T0 (assuming all emails just arrived right now):")
    print("  - t0_critical: Mark 'X' if should be in 🚨 CRITICAL")
    print("  - t0_today: Mark 'X' if should be in 📦 TODAY (deliveries, deadlines today)")
    print("  - t0_coming_up: Mark 'X' if should be in 📅 COMING UP (events 1-7 days)")
    print("  - t0_worth_knowing: Mark 'X' if should be in 💼 WORTH KNOWING")
    print("  - t0_everything_else: Mark 'X' if should be in footer")
    print("  - t0_skip: Mark 'X' if should not appear at all")
    print()
    print("PHASE 2: T1 Labeling (24 hours later)")
    print("-" * 80)
    print("Re-label each email for T1 (24 hours after emails arrived):")
    print("  - Events 'tomorrow' at T0 might be 'today' at T1")
    print("  - Events 'today' at T0 might be expired at T1 (skip)")
    print("  - Critical items might downgrade to routine")
    print()
    print("PHASE 3: T2 Labeling (168 hours / 1 week later)")
    print("-" * 80)
    print("Re-label each email for T2 (1 week after emails arrived):")
    print("  - Most time-sensitive items should be expired (skip)")
    print("  - Receipts/confirmations remain in worth_knowing")
    print("  - Future events might now be past events")
    print()
    print("TIPS:")
    print("  - Use 'temporal_hints' column to note time-related context")
    print("  - Example: 'event tomorrow', 'delivery today', 'bill due in 3 days'")
    print("  - This helps validate temporal decay logic")
    print()
    print("Run: python3 scripts/interactive_temporal_review.py")
    print("  to use the interactive terminal tool for labeling")
    print()
    print("=" * 80)
    print()
    print("Predicted importance distribution:")
    print(output_df["predicted_importance"].value_counts())
    print()
    print("Predicted type distribution:")
    print(output_df["predicted_type"].value_counts())

    return 0


if __name__ == "__main__":
    sys.exit(main())
