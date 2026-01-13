"""
Extracts structured entities (flights, events, deadlines) from emails.

Hybrid approach: rules-based extraction for common patterns (fast, high confidence)
with LLM fallback for edge cases. Validates metadata (thread_id, email_id) for linking.

Key: HybridExtractor.extract() → RulesExtractor → LLMExtractor (fallback).
"""

from __future__ import annotations

import os
import re

import google.generativeai as genai

from shopq.classification.extractor_patterns import (
    DEADLINE_PATTERNS,
    EVENT_PATTERNS,
    FLIGHT_PATTERNS,
    PROMO_PATTERNS,
    REMINDER_PATTERNS,
    categorize_notification,
    email_timestamp,
    extract_otp_expiry,
    extract_shipping_info,
    get_email_importance,
    parse_notification_timestamp,
    validate_entity_metadata,
)
from shopq.classification.models import (
    DeadlineEntity,
    Entity,
    EventEntity,
    FlightEntity,
    Location,
    NotificationEntity,
    PromoEntity,
    ReminderEntity,
)
from shopq.observability.logging import get_logger

logger = get_logger(__name__)


class RulesExtractor:
    """Rules-based entity extraction using regex patterns"""

    def __init__(self) -> None:
        # NOTE: ImportanceClassifier removed - using Gemini importance directly
        pass

    def extract_flight(self, email: dict) -> FlightEntity | None:
        """Extract flight information

        Side Effects:
            None (pure function - parses email text and builds FlightEntity)
        """
        text = f"{email.get('subject', '')} {email.get('snippet', '')}"

        # Check if this looks like a flight email
        if not any(
            word in text.lower() for word in ["flight", "boarding", "departure", "confirmation"]
        ):
            return None

        # Extract flight number
        flight_match = re.search(FLIGHT_PATTERNS["flight_number"], text, re.IGNORECASE)
        if not flight_match:
            return None

        flight_number = flight_match.group(1).strip()

        # Extract airline
        airline_match = re.search(FLIGHT_PATTERNS["airline"], text)
        airline = airline_match.group(1) if airline_match else None

        # Extract airport codes
        airport_codes = re.findall(FLIGHT_PATTERNS["airport_code"], text)

        # Extract time
        time_match = re.search(FLIGHT_PATTERNS["time"], text)
        departure_time = time_match.group(1) if time_match else None

        # Use Gemini importance from email (single source of truth)
        importance = get_email_importance(email)

        # Create entity
        return FlightEntity(
            confidence=0.9,  # High confidence for rules-based extraction
            source_email_id=email.get("id", ""),
            source_thread_id=email.get("thread_id", email.get("id", "")),
            source_subject=email.get("subject", ""),
            source_snippet=email.get("snippet", ""),
            timestamp=email_timestamp(email),
            importance=importance,
            airline=airline,
            flight_number=flight_number,
            departure=Location(airport_code=airport_codes[0] if len(airport_codes) > 0 else None),
            arrival=Location(airport_code=airport_codes[1] if len(airport_codes) > 1 else None),
            departure_time=departure_time,
        )

    def extract_event(self, email: dict) -> EventEntity | None:
        """Extract event information

        Side Effects:
            None (pure function - parses email text and builds EventEntity)
        """
        text = f"{email.get('subject', '')} {email.get('snippet', '')}"

        # Check for event indicators (including calendar notification formats)
        event_indicators = [
            "starts",
            "begins",
            "class",
            "event",
            "meeting",
            "appointment",
            "notification:",
            "reminder:",
            "meditation",
            "call",
        ]
        if not any(word in text.lower() for word in event_indicators):
            return None

        # Extract from subject - check calendar notification format FIRST
        subject = email.get("subject", "").strip()

        # Clean calendar notification format: "Notification: EVENT @ DATE TIME (TIMEZONE) (EMAIL)"
        calendar_match = re.match(
            r"^(?:Notification|Reminder):\s*(.+?)\s+@\s+.+", subject, re.IGNORECASE
        )
        if calendar_match:
            # Extract clean event name before the "@" symbol
            title = calendar_match.group(1).strip()
        else:
            # Try "don't forget" style from snippet/body
            dont_forget_match = re.search(EVENT_PATTERNS["dont_forget"], text, re.IGNORECASE)
            title = dont_forget_match.group(1).strip() if dont_forget_match else subject

        # Extract time (check for time range first, then single time)
        event_end_time = None
        time_range_match = re.search(EVENT_PATTERNS["event_time_range"], text)
        if time_range_match:
            event_time = time_range_match.group(1)
            event_end_time = time_range_match.group(2)
        else:
            time_match = re.search(EVENT_PATTERNS["event_time"], text)
            event_time = time_match.group(1) if time_match else None

        # Check for "starts soon" patterns
        starts_soon = re.search(EVENT_PATTERNS["starts_soon"], text, re.IGNORECASE)
        if starts_soon:
            when = starts_soon.group(1)
            event_time = f"{when} at {event_time}" if event_time else when

        # Extract location if available
        location = None
        location_in = re.search(EVENT_PATTERNS["location_in"], text)
        location_at = re.search(EVENT_PATTERNS["location_at"], text)

        if location_in:
            city = location_in.group(1).strip()
            location = Location(city=city)
        elif location_at:
            place = location_at.group(1).strip()
            if len(place.split()) <= 2:
                location = Location(city=place)
            else:
                location = Location(full_address=place)

        importance = get_email_importance(email)

        return EventEntity(
            confidence=0.85,
            source_email_id=email.get("id", ""),
            source_thread_id=email.get("thread_id", email.get("id", "")),
            source_subject=email.get("subject", ""),
            source_snippet=email.get("snippet", ""),
            timestamp=email_timestamp(email),
            importance=importance,
            title=title,
            event_time=event_time,
            event_end_time=event_end_time,
            location=location,
            organizer=email.get("from_name"),
        )

    def extract_deadline(self, email: dict) -> DeadlineEntity | None:
        """Extract deadline information (bills, payments)

        Side Effects:
            None (pure function - parses email text and builds DeadlineEntity)
        """
        text = f"{email.get('subject', '')} {email.get('snippet', '')}"

        bill_match = re.search(DEADLINE_PATTERNS["bill_due"], text, re.IGNORECASE)
        if not bill_match:
            return None

        title = f"{bill_match.group(1).capitalize()} due"
        due_date = bill_match.group(2) if (bill_match.lastindex or 0) >= 2 else None

        amount_match = re.search(DEADLINE_PATTERNS["amount"], text)
        amount = f"${amount_match.group(1)}" if amount_match else None

        importance = get_email_importance(email)

        return DeadlineEntity(
            confidence=0.9,
            source_email_id=email.get("id", ""),
            source_thread_id=email.get("thread_id", email.get("id", "")),
            source_subject=email.get("subject", ""),
            source_snippet=email.get("snippet", ""),
            timestamp=email_timestamp(email),
            importance=importance,
            title=title,
            due_date=due_date,
            amount=amount,
            from_whom=email.get("from_name"),
        )

    def extract_reminder(self, email: dict) -> ReminderEntity | None:
        """Extract reminder information

        Side Effects:
            None (pure function - parses email text and builds ReminderEntity)
        """
        text = f"{email.get('subject', '')} {email.get('snippet', '')}"

        if not any(
            word in text.lower() for word in ["time to", "schedule", "reminder", "don't forget"]
        ):
            return None

        schedule_match = re.search(REMINDER_PATTERNS["schedule"], text, re.IGNORECASE)
        renew_match = re.search(REMINDER_PATTERNS["renew"], text, re.IGNORECASE)

        if schedule_match:
            action = f"schedule {schedule_match.group(1).strip()}"
        elif renew_match:
            action = f"renew {renew_match.group(1).strip()}"
        else:
            action = email.get("snippet", "")[:100]

        importance = get_email_importance(email)

        return ReminderEntity(
            confidence=0.8,
            source_email_id=email.get("id", ""),
            source_thread_id=email.get("thread_id", email.get("id", "")),
            source_subject=email.get("subject", ""),
            source_snippet=email.get("snippet", ""),
            timestamp=email_timestamp(email),
            importance=importance,
            from_sender=email.get("from_name"),
            action=action,
        )

    def extract_promo(self, email: dict) -> PromoEntity | None:
        """Extract promotional offer information

        Side Effects:
            None (pure function - parses email text and builds PromoEntity)
        """
        text = f"{email.get('subject', '')} {email.get('snippet', '')}"

        if email.get("type") != "promotion":
            return None

        discount_match = re.search(PROMO_PATTERNS["discount"], text)
        offer = discount_match.group(1) + " off" if discount_match else None

        ends_match = re.search(PROMO_PATTERNS["ends"], text, re.IGNORECASE)
        expiry = f"ends {ends_match.group(1)}" if ends_match else None

        merchant = email.get("from_name", "").split("@")[0]

        return PromoEntity(
            confidence=0.85,
            source_email_id=email.get("id", ""),
            source_thread_id=email.get("thread_id", email.get("id", "")),
            source_subject=email.get("subject", ""),
            source_snippet=email.get("snippet", ""),
            timestamp=email_timestamp(email),
            importance="routine",  # Promos are usually routine
            merchant=merchant,
            offer=offer,
            expiry=expiry,
        )

    def extract_notification(self, email: dict) -> NotificationEntity | None:
        """Extract generic notification (fraud alerts, package delivery, job opportunities, etc.)

        Side Effects:
            None (pure function - parses email text and builds NotificationEntity)
        """
        text = f"{email.get('subject', '')} {email.get('snippet', '')}"
        text_lower = text.lower()

        # Determine category based on content
        category = categorize_notification(text_lower, email.get("type"))
        if not category:
            return None

        importance = get_email_importance(email)
        notif_timestamp = parse_notification_timestamp(email)

        # Extract OTP expiry (for temporal decay)
        otp_expires_at = extract_otp_expiry(text_lower, notif_timestamp)

        # Extract shipping info for delivery notifications
        ship_status, delivered_at, tracking_number = None, None, None
        if category == "delivery":
            ship_status, delivered_at, tracking_number = extract_shipping_info(
                text_lower, text, notif_timestamp
            )

        return NotificationEntity(
            confidence=0.75,
            source_email_id=email.get("id", ""),
            source_thread_id=email.get("thread_id", email.get("id", "")),
            source_subject=email.get("subject", ""),
            source_snippet=email.get("snippet", ""),
            timestamp=notif_timestamp,
            importance=importance,
            category=category,
            message=email.get("snippet", "")[:200],
            action_required=(email.get("attention") == "action_required"),
            otp_expires_at=otp_expires_at,
            ship_status=ship_status,
            delivered_at=delivered_at,
            tracking_number=tracking_number,
        )

    def extract_all(self, email: dict) -> list[Entity]:
        """Try all extractors on an email

        Side Effects:
            - Logs exceptions if any extractor fails (via logger.exception)
        """
        entities: list[Entity] = []

        extractors = [
            self.extract_flight,
            self.extract_event,
            self.extract_deadline,
            self.extract_reminder,
            self.extract_promo,
            self.extract_notification,
        ]

        for extractor in extractors:
            try:
                entity = extractor(email)
                if entity:
                    entities.append(entity)
                    # Only extract one entity per email for now
                    break
            except Exception as e:
                logger.exception("Error in %s: %s", extractor.__name__, e)
                continue

        return entities


class LLMExtractor:
    """LLM-based entity extraction for complex cases"""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash-exp")
        else:
            self.model = None

    def extract(self, _email: dict) -> Entity | None:
        """
        Extract entity using LLM (fallback for complex cases)

        Future Enhancement:
        - Use Gemini structured output to extract entities from complex emails
        - Fallback when rules-based extraction fails
        - Lower confidence than rules (0.6-0.7 range)

        For MVP: Returns None, relies entirely on rules-based extraction

        Side Effects:
            None (pure function - currently returns None, future: may call Gemini API)
        """
        if not self.model:
            return None

        # Not yet implemented - rules-based extraction handles 90%+ of cases
        return None


class HybridExtractor:
    """Hybrid entity extractor: rules first, LLM fallback"""

    def __init__(self):
        self.rules_extractor = RulesExtractor()
        self.llm_extractor = LLMExtractor()

    def extract_from_email(self, email: dict) -> list[Entity]:
        """Extract entities from a single email

        Side Effects:
            - Logs exceptions if extraction fails (via RulesExtractor.extract_all)
        """
        # Try rules first
        entities = self.rules_extractor.extract_all(email)

        if entities:
            return entities

        # Fallback to LLM if no rules matched
        llm_entity = self.llm_extractor.extract(email)
        if llm_entity:
            return [llm_entity]

        return []

    def extract_from_emails(self, emails: list[dict]) -> list[Entity]:
        """Extract entities from multiple emails

        Side Effects:
            - Logs exceptions if extraction fails for any email (via extract_from_email)
            - Logs warnings for invalid entities (via logger.warning)
        """
        all_entities = []

        for email in emails:
            entities = self.extract_from_email(email)

            # PRIORITY 6 FIX: Validate metadata for each extracted entity
            validated_entities = []
            for entity in entities:
                validated_entity = validate_entity_metadata(entity, email)
                validated_entities.append(validated_entity)

            all_entities.extend(validated_entities)

        return all_entities
