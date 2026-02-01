#!/usr/bin/env python3
"""
Golden Dataset Labeler (v0.1)

Creates ground-truth ORDER ENTITIES from Gmail Purchases sample for evaluating:
1) Order entity grouping (dedupe/merge/miss)
2) Extraction correctness for merchant order numbers and tracking numbers

Usage:
    uv run python scripts/golden_dataset_labeler.py data/labeling/emails.jsonl

Outputs:
    - emails_golden.csv: email_id, thread_id, bucket, role
    - orders_golden.csv: order_id, merchant_domain, merchant_order_id, tracking_number,
                         policy, anchor, evidence_email_id

Key concept:
    O-### is the human-created cluster ID (ground truth bucket).
    merchant_order_id is the actual order number from the merchant (e.g., "ILIA2983241").
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# === Constants ===

NOISE = "NOISE"
BLOCKLIST = "BLOCKLIST"
VALID_ROLES = {"confirmation", "shipping", "delivery", "other"}
VALID_ANCHORS = {"delivery", "purchase", "none"}

# Regex patterns for auto-detection
ORDER_ID_PATTERNS = [
    r"Order\s*#\s*:?\s*([A-Z0-9-]+)",
    r"Order\s+Number\s*:?\s*([A-Z0-9-]+)",
    r"Confirmation\s*#\s*:?\s*([A-Z0-9-]+)",
    r"Order\s+ID\s*:?\s*([A-Z0-9-]+)",
    r"#([A-Z]{2,}[0-9]+)",  # e.g., #ILIA2983241
    r"(\d{3}-\d{7}-\d{7})",  # Amazon format
]

TRACKING_PATTERNS = [
    r"Tracking\s*(?:#|Number)\s*:?\s*([A-Z0-9]+)",
    r"Track(?:ing)?\s*:\s*([A-Z0-9]+)",
    r"(1Z[A-Z0-9]{16})",  # UPS
    r"(\d{20,22})",  # FedEx/USPS long numbers
]


# === Auto-detection ===

def detect_order_id(text: str) -> str | None:
    """Try to extract merchant order ID from text."""
    for pattern in ORDER_ID_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def detect_tracking(text: str) -> str | None:
    """Try to extract tracking number from text."""
    for pattern in TRACKING_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# === Data Models ===

@dataclass
class Email:
    """An email to be labeled."""
    email_id: str
    thread_id: str = ""
    from_addr: str = ""
    subject: str = ""
    snippet: str = ""
    internal_date_ms: int = 0

    # Labels
    bucket: str = ""  # O-### | NOISE | BLOCKLIST
    role: str = ""    # confirmation | shipping | delivery | other (only if O-###)

    @property
    def date_str(self) -> str:
        if self.internal_date_ms:
            dt = datetime.fromtimestamp(self.internal_date_ms / 1000)
            return dt.strftime("%Y-%m-%d %H:%M")
        return ""

    @property
    def domain(self) -> str:
        if "<" in self.from_addr and ">" in self.from_addr:
            email = self.from_addr.split("<")[1].split(">")[0]
        else:
            email = self.from_addr
        return email.split("@")[-1] if "@" in email else ""

    @property
    def is_labeled(self) -> bool:
        if not self.bucket:
            return False
        if self.bucket.startswith("O-"):
            return bool(self.role)
        return True  # NOISE or BLOCKLIST don't need role


@dataclass
class Order:
    """An order entity with policy info."""
    order_id: str                    # O-### (human-created cluster ID)
    merchant_domain: str = ""        # e.g., "amazon.com"
    merchant_order_id: str = ""      # The actual order number (e.g., "ILIA2983241")
    tracking_number: str = ""        # Shipping tracking number
    policy: str = "unknown"          # exact:YYYY-MM-DD | days:NN | unknown
    anchor: str = "none"             # delivery | purchase | none
    evidence_email_id: str = ""


@dataclass
class State:
    """Persisted labeling state."""
    emails: list[Email] = field(default_factory=list)
    orders: dict[str, Order] = field(default_factory=dict)
    cursor: int = 0
    order_cursor: int = 0
    next_order_num: int = 1

    def create_order(self, merchant_domain: str = "") -> str:
        """Create new order and return its ID."""
        order_id = f"O-{self.next_order_num:03d}"
        self.next_order_num += 1
        self.orders[order_id] = Order(order_id=order_id, merchant_domain=merchant_domain)
        return order_id

    @property
    def current_email(self) -> Email | None:
        if 0 <= self.cursor < len(self.emails):
            return self.emails[self.cursor]
        return None

    @property
    def order_list(self) -> list[Order]:
        return sorted(self.orders.values(), key=lambda o: o.order_id)

    @property
    def current_order(self) -> Order | None:
        orders = self.order_list
        if 0 <= self.order_cursor < len(orders):
            return orders[self.order_cursor]
        return None


# === Persistence ===

def load_emails(path: Path) -> list[Email]:
    """Load emails from JSONL."""
    emails = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            emails.append(Email(
                email_id=data.get("email_id", ""),
                thread_id=data.get("thread_id", ""),
                from_addr=data.get("from", ""),
                subject=data.get("subject", ""),
                snippet=data.get("snippet", ""),
                internal_date_ms=data.get("internal_date_ms", 0),
            ))
    return emails


def load_state(state_path: Path, emails: list[Email]) -> State:
    """Load state from JSON, merging with current emails."""
    if not state_path.exists():
        return State(emails=emails)

    with open(state_path) as f:
        data = json.load(f)

    # Build lookup of saved labels
    saved_labels = {e["email_id"]: e for e in data.get("emails", [])}

    # Apply saved labels to current emails
    for email in emails:
        if email.email_id in saved_labels:
            saved = saved_labels[email.email_id]
            email.bucket = saved.get("bucket", "")
            email.role = saved.get("role", "")

    # Load orders
    orders = {}
    for o in data.get("orders", []):
        orders[o["order_id"]] = Order(
            order_id=o["order_id"],
            merchant_domain=o.get("merchant_domain", ""),
            merchant_order_id=o.get("merchant_order_id", ""),
            tracking_number=o.get("tracking_number", ""),
            policy=o.get("policy", "unknown"),
            anchor=o.get("anchor", "none"),
            evidence_email_id=o.get("evidence_email_id", ""),
        )

    return State(
        emails=emails,
        orders=orders,
        cursor=data.get("cursor", 0),
        order_cursor=data.get("order_cursor", 0),
        next_order_num=data.get("next_order_num", 1),
    )


def save_state(state: State, state_path: Path) -> None:
    """Save state to JSON."""
    data = {
        "emails": [
            {
                "email_id": e.email_id,
                "bucket": e.bucket,
                "role": e.role,
            }
            for e in state.emails
        ],
        "orders": [
            {
                "order_id": o.order_id,
                "merchant_domain": o.merchant_domain,
                "merchant_order_id": o.merchant_order_id,
                "tracking_number": o.tracking_number,
                "policy": o.policy,
                "anchor": o.anchor,
                "evidence_email_id": o.evidence_email_id,
            }
            for o in state.orders.values()
        ],
        "cursor": state.cursor,
        "order_cursor": state.order_cursor,
        "next_order_num": state.next_order_num,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(data, f, indent=2)


# === Validation ===

def validate(state: State) -> list[str]:
    """Validate labels. Returns list of errors."""
    errors = []

    for email in state.emails:
        if not email.bucket:
            errors.append(f"{email.email_id}: missing bucket")
        elif email.bucket.startswith("O-"):
            if not email.role:
                errors.append(f"{email.email_id}: O-### bucket requires role")
            elif email.role not in VALID_ROLES:
                errors.append(f"{email.email_id}: invalid role '{email.role}'")
        elif email.bucket in (NOISE, BLOCKLIST):
            if email.role:
                errors.append(f"{email.email_id}: {email.bucket} should not have role")
        else:
            errors.append(f"{email.email_id}: invalid bucket '{email.bucket}'")

    return errors


# === Export ===

def export_csvs(state: State, output_dir: Path) -> bool:
    """Export to CSVs. Returns True if successful."""
    errors = validate(state)
    if errors:
        print(f"\n{'='*60}")
        print("VALIDATION ERRORS - Cannot export")
        print('='*60)
        for err in errors[:20]:
            print(f"  {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    # emails_golden.csv
    emails_path = output_dir / "emails_golden.csv"
    with open(emails_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email_id", "thread_id", "bucket", "role"])
        for email in state.emails:
            writer.writerow([
                email.email_id,
                email.thread_id,
                email.bucket,
                email.role if email.bucket.startswith("O-") else "",
            ])
    print(f"Wrote {emails_path}")

    # orders_golden.csv
    orders_path = output_dir / "orders_golden.csv"
    with open(orders_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "merchant_domain", "merchant_order_id", "tracking_number", "policy", "anchor", "evidence_email_id"])
        for order in state.order_list:
            writer.writerow([
                order.order_id,
                order.merchant_domain,
                order.merchant_order_id,
                order.tracking_number,
                order.policy,
                order.anchor,
                order.evidence_email_id,
            ])
    print(f"Wrote {orders_path}")

    return True


# === CLI ===

class Labeler:
    """Interactive labeling CLI."""

    def __init__(self, state: State, state_path: Path, output_dir: Path):
        self.state = state
        self.state_path = state_path
        self.output_dir = output_dir
        self.undo_stack: list[tuple[str, str, str, str]] = []  # (email_id, old_bucket, old_role, action)

    def save(self) -> None:
        save_state(self.state, self.state_path)

    def push_undo(self, email: Email, action: str) -> None:
        self.undo_stack.append((email.email_id, email.bucket, email.role, action))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        email_id, old_bucket, old_role, action = self.undo_stack.pop()
        for email in self.state.emails:
            if email.email_id == email_id:
                email.bucket = old_bucket
                email.role = old_role
                return True
        return False

    def show_progress(self) -> None:
        total = len(self.state.emails)
        labeled = sum(1 for e in self.state.emails if e.is_labeled)
        orders = len(self.state.orders)
        noise = sum(1 for e in self.state.emails if e.bucket == NOISE)
        blocklist = sum(1 for e in self.state.emails if e.bucket == BLOCKLIST)

        print(f"\n{'='*60}")
        print(f"Progress: {labeled}/{total} labeled ({100*labeled//total}%)")
        print(f"Orders: {orders}  |  NOISE: {noise}  |  BLOCKLIST: {blocklist}")
        print('='*60)

    def show_email(self) -> None:
        email = self.state.current_email
        if not email:
            print("\n(no email to display)")
            return

        pos = self.state.cursor + 1
        total = len(self.state.emails)

        print(f"\n[{pos}/{total}] {email.email_id}")
        print(f"{'─'*60}")
        print(f"Date:    {email.date_str}")
        print(f"From:    {email.from_addr}")
        print(f"Domain:  {email.domain}")
        print(f"Subject: {email.subject[:70]}")
        print(f"Snippet: {email.snippet[:100]}...")
        if email.thread_id:
            thread_count = sum(1 for e in self.state.emails if e.thread_id == email.thread_id)
            print(f"Thread:  {email.thread_id[:20]}... ({thread_count} emails)")
        print(f"{'─'*60}")

        # Auto-detected candidates
        text = f"{email.subject} {email.snippet}"
        detected_order = detect_order_id(text)
        detected_tracking = detect_tracking(text)
        if detected_order or detected_tracking:
            print(f"Detected: ", end="")
            parts = []
            if detected_order:
                parts.append(f"order={detected_order}")
            if detected_tracking:
                parts.append(f"tracking={detected_tracking}")
            print(" | ".join(parts))

        # Current label
        if email.bucket:
            label = email.bucket
            if email.role:
                label += f" ({email.role})"
            status = "✓" if email.is_labeled else "⚠️ needs role"
            print(f"Label:   {label}  {status}")
        else:
            print("Label:   (unlabeled)")

        # Quick commands
        print(f"{'─'*60}")
        print("  o=new order  m O-###=assign  n=NOISE  x=BLOCKLIST")
        print("  r c|s|d|o=set role  t=thread  Enter=next  ?=help")

    def show_thread(self) -> None:
        email = self.state.current_email
        if not email or not email.thread_id:
            print("No thread for this email")
            return

        thread_emails = [e for e in self.state.emails if e.thread_id == email.thread_id]
        thread_emails.sort(key=lambda e: e.internal_date_ms)

        print(f"\n{'='*60}")
        print(f"Thread: {email.thread_id[:30]}... ({len(thread_emails)} emails)")
        print('='*60)

        for i, e in enumerate(thread_emails):
            marker = ">>>" if e.email_id == email.email_id else "   "
            label = e.bucket or "(unlabeled)"
            if e.role:
                label += f"/{e.role}"
            print(f"{marker} {i+1}. {e.date_str} | {label:20} | {e.subject[:40]}")

    def bulk_assign_thread(self, bucket: str, role: str = "") -> int:
        """Assign all emails in current thread to bucket. Returns count."""
        email = self.state.current_email
        if not email or not email.thread_id:
            return 0

        count = 0
        for e in self.state.emails:
            if e.thread_id == email.thread_id and e.bucket != bucket:
                self.push_undo(e, "thread_assign")
                e.bucket = bucket
                if role and bucket.startswith("O-"):
                    e.role = role
                count += 1
        return count

    def find_next_unlabeled(self, forward: bool = True) -> int | None:
        """Find next/previous unlabeled email index."""
        emails = self.state.emails
        start = self.state.cursor

        if forward:
            for i in range(start + 1, len(emails)):
                if not emails[i].is_labeled:
                    return i
            for i in range(0, start):
                if not emails[i].is_labeled:
                    return i
        else:
            for i in range(start - 1, -1, -1):
                if not emails[i].is_labeled:
                    return i
            for i in range(len(emails) - 1, start, -1):
                if not emails[i].is_labeled:
                    return i
        return None

    def show_help(self) -> None:
        print(f"""
{'='*60}
GOLDEN DATASET LABELER - HELP
{'='*60}

BUCKET ASSIGNMENT:
  o             Create new order O-### and assign this email
                (auto-detects order# and tracking from email)
  m <O-###>     Assign email to existing order (e.g., m O-001)
  n             Set bucket = NOISE (purchase-adjacent junk)
  x             Set bucket = BLOCKLIST (grocery/digital/subscription)

ROLE (required for O-### buckets):
  r c           Role = confirmation (order placed)
  r s           Role = shipping (shipped notification)
  r d           Role = delivery (delivered notification)
  r o           Role = other (RMA, return label, etc.)

THREAD:
  t             Show all emails in this thread
  ta            Assign entire thread to current email's bucket
  ta <O-###>    Assign entire thread to specified order

NAVIGATION:
  Enter         Next email
  p             Previous email
  nu            Next unlabeled
  pu            Previous unlabeled
  g <N>         Go to email N (1-indexed)

OTHER:
  u             Undo last change
  save          Export CSVs (validates first)
  orders        Switch to order mode (set order#, tracking, policy)
  ?             Show this help
  q             Quit (auto-saves)

{'='*60}
""")

    def run_email_mode(self) -> str | None:
        """Run email labeling pass. Returns 'orders' to switch, None to quit."""
        self.show_progress()
        self.show_email()

        while True:
            try:
                cmd = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None

            parts = cmd.split(None, 1)
            action = parts[0].lower() if parts else ""
            arg = parts[1] if len(parts) > 1 else ""

            email = self.state.current_email

            # === Bucket assignment ===
            if action == "o":
                # Create new order
                if email:
                    order_id = self.state.create_order(merchant_domain=email.domain)
                    self.push_undo(email, "new_order")
                    email.bucket = order_id
                    email.role = ""  # Needs role assignment

                    # Auto-detect and store merchant_order_id / tracking
                    text = f"{email.subject} {email.snippet}"
                    order = self.state.orders[order_id]
                    detected_order = detect_order_id(text)
                    detected_tracking = detect_tracking(text)
                    if detected_order:
                        order.merchant_order_id = detected_order
                        print(f"Created {order_id} (order#: {detected_order})")
                    else:
                        print(f"Created {order_id}")
                    if detected_tracking:
                        order.tracking_number = detected_tracking
                        print(f"  (tracking: {detected_tracking})")
                    self.save()
                self.show_email()

            elif action == "m" and arg:
                # Assign to existing order
                order_id = arg.upper()
                if email:
                    if order_id in self.state.orders:
                        self.push_undo(email, "assign")
                        email.bucket = order_id
                        email.role = ""  # May need role update

                        # Auto-detect and store if order doesn't have them yet
                        text = f"{email.subject} {email.snippet}"
                        order = self.state.orders[order_id]
                        if not order.merchant_order_id:
                            detected = detect_order_id(text)
                            if detected:
                                order.merchant_order_id = detected
                                print(f"Assigned to {order_id} (order#: {detected})")
                            else:
                                print(f"Assigned to {order_id}")
                        else:
                            print(f"Assigned to {order_id}")
                        if not order.tracking_number:
                            detected = detect_tracking(text)
                            if detected:
                                order.tracking_number = detected
                                print(f"  (tracking: {detected})")
                        self.save()
                    else:
                        print(f"Order {order_id} doesn't exist")
                self.show_email()

            elif action == "n":
                # NOISE
                if email:
                    self.push_undo(email, "noise")
                    email.bucket = NOISE
                    email.role = ""
                    self.save()
                # Auto-advance
                if self.state.cursor < len(self.state.emails) - 1:
                    self.state.cursor += 1
                self.show_email()

            elif action == "x":
                # BLOCKLIST
                if email:
                    self.push_undo(email, "blocklist")
                    email.bucket = BLOCKLIST
                    email.role = ""
                    self.save()
                # Auto-advance
                if self.state.cursor < len(self.state.emails) - 1:
                    self.state.cursor += 1
                self.show_email()

            # === Role assignment ===
            elif action == "r" and arg:
                role_map = {"c": "confirmation", "s": "shipping", "d": "delivery", "o": "other"}
                role = role_map.get(arg.lower(), arg.lower())
                if email:
                    if not email.bucket.startswith("O-"):
                        print("Role only valid for O-### buckets")
                    elif role not in VALID_ROLES:
                        print(f"Invalid role. Use: c/s/d/o or {VALID_ROLES}")
                    else:
                        self.push_undo(email, "role")
                        email.role = role
                        self.save()
                        # Auto-advance if now fully labeled
                        if email.is_labeled and self.state.cursor < len(self.state.emails) - 1:
                            self.state.cursor += 1
                self.show_email()

            # === Thread ===
            elif action == "t" and not arg:
                self.show_thread()

            elif action == "ta":
                if email:
                    if arg:
                        bucket = arg.upper()
                    elif email.bucket:
                        bucket = email.bucket
                    else:
                        print("Specify bucket: ta <O-###> or ta n or ta x")
                        continue

                    if bucket.startswith("O-") and bucket not in self.state.orders:
                        print(f"Order {bucket} doesn't exist")
                        continue

                    count = self.bulk_assign_thread(bucket)
                    print(f"Assigned {count} emails to {bucket}")
                    self.save()
                self.show_email()

            # === Navigation ===
            elif not cmd:
                # Next
                if self.state.cursor < len(self.state.emails) - 1:
                    self.state.cursor += 1
                    self.save()
                self.show_email()

            elif action == "p":
                # Previous
                if self.state.cursor > 0:
                    self.state.cursor -= 1
                    self.save()
                self.show_email()

            elif action == "nu":
                # Next unlabeled
                idx = self.find_next_unlabeled(forward=True)
                if idx is not None:
                    self.state.cursor = idx
                    self.save()
                else:
                    print("No unlabeled emails remaining!")
                self.show_email()

            elif action == "pu":
                # Previous unlabeled
                idx = self.find_next_unlabeled(forward=False)
                if idx is not None:
                    self.state.cursor = idx
                    self.save()
                else:
                    print("No unlabeled emails remaining!")
                self.show_email()

            elif action == "g" and arg:
                # Go to
                try:
                    idx = int(arg) - 1
                    if 0 <= idx < len(self.state.emails):
                        self.state.cursor = idx
                        self.save()
                    else:
                        print(f"Invalid index. Range: 1-{len(self.state.emails)}")
                except ValueError:
                    print("Usage: g <number>")
                self.show_email()

            # === Other ===
            elif action == "u":
                if self.undo():
                    print("Undone")
                    self.save()
                else:
                    print("Nothing to undo")
                self.show_email()

            elif action == "save":
                if export_csvs(self.state, self.output_dir):
                    print("Export complete!")

            elif action == "orders":
                return "orders"

            elif action in ("?", "help"):
                self.show_help()

            elif action == "q":
                self.save()
                return None

            else:
                print(f"Unknown: {cmd}. Type ? for help.")

    def show_order(self) -> None:
        order = self.state.current_order
        if not order:
            print("\n(no order to display)")
            return

        pos = self.state.order_cursor + 1
        total = len(self.state.orders)

        # Get emails for this order
        order_emails = [e for e in self.state.emails if e.bucket == order.order_id]
        order_emails.sort(key=lambda e: e.internal_date_ms)

        print(f"\n{'='*60}")
        print(f"[{pos}/{total}] {order.order_id}  |  {order.merchant_domain or '(no domain)'}")
        print('='*60)

        print(f"\nOrder#:   {order.merchant_order_id or '(not set)'}")
        print(f"Tracking: {order.tracking_number or '(not set)'}")
        print(f"Policy:   {order.policy}")
        print(f"Anchor:   {order.anchor}")
        print(f"Evidence: {order.evidence_email_id or '(none)'}")

        print(f"\nEmails ({len(order_emails)}):")
        for i, e in enumerate(order_emails):
            evidence = " [evidence]" if e.email_id == order.evidence_email_id else ""
            print(f"  {i+1}. [{e.role:12}] {e.date_str} | {e.subject[:40]}{evidence}")

        print(f"{'─'*60}")
        print("  id <text>   Set merchant order number")
        print("  tr <text>   Set tracking number")
        print("  policy exact:YYYY-MM-DD | days:NN | unknown")
        print("  anchor delivery | purchase | none")
        print("  Enter=next  p=prev  emails=back  ?=help")

    def run_order_mode(self) -> str | None:
        """Run order policy labeling pass. Returns 'emails' to switch, None to quit."""
        if not self.state.orders:
            print("\nNo orders to label. Create orders in email mode first.")
            return "emails"

        print("\n" + "="*60)
        print("ORDER POLICY MODE")
        print("="*60)
        self.show_order()

        while True:
            try:
                cmd = input("\n[order]> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None

            parts = cmd.split(None, 1)
            action = parts[0].lower() if parts else ""
            arg = parts[1] if len(parts) > 1 else ""

            order = self.state.current_order

            # === Order identifiers ===
            if action == "id":
                if order:
                    order.merchant_order_id = arg
                    self.save()
                    print(f"Set order# = {arg or '(cleared)'}")
                self.show_order()

            elif action == "tr":
                if order:
                    order.tracking_number = arg
                    self.save()
                    print(f"Set tracking = {arg or '(cleared)'}")
                self.show_order()

            elif action == "policy" and arg:
                if order:
                    # Validate policy format
                    if arg == "unknown" or arg.startswith("exact:") or arg.startswith("days:"):
                        order.policy = arg
                        self.save()
                        print(f"Set policy = {arg}")
                    else:
                        print("Format: exact:YYYY-MM-DD | days:NN | unknown")
                self.show_order()

            elif action == "anchor" and arg:
                if order:
                    if arg in VALID_ANCHORS:
                        order.anchor = arg
                        self.save()
                        print(f"Set anchor = {arg}")
                    else:
                        print(f"Invalid anchor. Use: {VALID_ANCHORS}")
                self.show_order()

            elif action == "evidence" and arg:
                if order:
                    order_emails = [e for e in self.state.emails if e.bucket == order.order_id]
                    order_emails.sort(key=lambda e: e.internal_date_ms)
                    try:
                        idx = int(arg) - 1
                        if 0 <= idx < len(order_emails):
                            order.evidence_email_id = order_emails[idx].email_id
                            self.save()
                            print(f"Set evidence = {order.evidence_email_id[:30]}...")
                        else:
                            print(f"Invalid. Range: 1-{len(order_emails)}")
                    except ValueError:
                        print("Usage: evidence <number>")
                self.show_order()

            elif not cmd:
                # Next
                if self.state.order_cursor < len(self.state.orders) - 1:
                    self.state.order_cursor += 1
                    self.save()
                self.show_order()

            elif action == "p":
                # Previous
                if self.state.order_cursor > 0:
                    self.state.order_cursor -= 1
                    self.save()
                self.show_order()

            elif action == "emails":
                return "emails"

            elif action == "save":
                if export_csvs(self.state, self.output_dir):
                    print("Export complete!")

            elif action in ("?", "help"):
                print(f"""
ORDER COMMANDS:
  id <text>                 Set merchant order number (e.g., "ILIA2983241")
  tr <text>                 Set tracking number

  policy exact:YYYY-MM-DD   Set explicit return-by date
  policy days:NN            Set return window in days
  policy unknown            No policy info available

  anchor delivery           Deadline anchored to delivery date
  anchor purchase           Deadline anchored to purchase date
  anchor none               No anchor

  evidence <N>              Set evidence email (by number in list)

  Enter                     Next order
  p                         Previous order
  emails                    Back to email labeling
  save                      Export CSVs
  q                         Quit
""")

            elif action == "q":
                self.save()
                return None

            else:
                print(f"Unknown: {cmd}. Type ? for help.")

    def run(self) -> None:
        """Main loop."""
        mode = "emails"

        while mode:
            if mode == "emails":
                mode = self.run_email_mode()
            elif mode == "orders":
                mode = self.run_order_mode()

        print("\nGoodbye!")


# === Main ===

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Golden Dataset Labeler")
    parser.add_argument("input_file", type=Path, help="Input JSONL file")
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("data/golden"),
        help="Output directory for CSVs",
    )
    parser.add_argument(
        "--state-file", "-s",
        type=Path,
        default=None,
        help="State file path (default: <output_dir>/labels_state.json)",
    )
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Error: Input file not found: {args.input_file}")
        sys.exit(1)

    state_path = args.state_file or (args.output_dir / "labels_state.json")

    print("="*60)
    print("GOLDEN DATASET LABELER v0")
    print("="*60)
    print(f"Input:  {args.input_file}")
    print(f"Output: {args.output_dir}")
    print(f"State:  {state_path}")

    # Load emails
    print("\nLoading emails...")
    emails = load_emails(args.input_file)
    print(f"Loaded {len(emails)} emails")

    # Load or resume state
    if state_path.exists():
        print(f"\nFound existing state at {state_path}")
        resume = input("Resume previous session? [Y/n] ").strip().lower()
        if resume in ("", "y", "yes"):
            state = load_state(state_path, emails)
            print("Resumed!")
        else:
            state = State(emails=emails)
            print("Starting fresh")
    else:
        state = State(emails=emails)

    # Run labeler
    labeler = Labeler(state, state_path, args.output_dir)
    labeler.run()


if __name__ == "__main__":
    main()
