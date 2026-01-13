# MailQ Email Classification Taxonomy

This document defines the complete taxonomy for classifying emails in MailQ, including type, importance, client labels, and temporality rules.

```yaml
mailq_taxonomy:
  type:
    event:
      definition: "Emails tied to attending something at a specific date/time."
      includes:
        - invitations
        - confirmations_with_access_info
        - event_access_links   # Zoom links, ticket barcodes, join URLs
        - reminders
        - day_of_event emails
        - classes / lectures / spiritual gatherings
        - community_meetups
        - group meetings
      excludes:
        - marketing_event_promotions_only
        - shipping_updates
        - generic system_notifications
      signals:
        - "Missing this email affects your ability to attend something."
        - "Contains or implies a real date/time for attendance."
        - "Often includes a location or virtual meeting link."

    notification:
      definition: "Operational updates about an account, security, or system status (NOT related to purchases)."
      includes:
        - account_security_alerts
        - password_resets
        - subscription_changes
        - billing_notifications (statements, upcoming charges)
        - system_activity_alerts
        - service_status_updates
      excludes:
        - purchase_related_emails (those are receipts)
        - editorial_content (newsletters)
        - marketing/promotional blasts
        - human_conversation_threads
      signals:
        - "It informs you about something that happened or changed in a system."
        - "Not about a purchase or payment."
        - "Not primarily a sales pitch."
        - "Not a human conversation, even if addressed personally."

    newsletter:
      definition: "Editorial, informational, or educational content, usually recurring and content-focused."
      includes:
        - substack_posts
        - editorial_roundups
        - community_updates
        - local_city_newsletters (e.g., 730DC)
        - listserv_announcements_without_direct_action_required
        - long_form_thought_pieces
      excludes:
        - transactional notifications
        - security alerts
        - personal messages
        - pure promotions
      signals:
        - "Informational or reflective tone."
        - "Often has 'View in browser' or newsletter branding."
        - "You read it for content, not to fix something."

    promotion:
      definition: "Commercial emails primarily intended to sell or push a product, service, or event."
      includes:
        - discounts and sales
        - product_launches
        - marketing_event_invites
        - branded_campaigns
        - cross_sells / up_sells
      excludes:
        - neutral transactional notices
        - non-commercial community updates
        - human one-off invites with no marketing framing
      signals:
        - "Would still feel like a sales pitch if you removed any dates."
        - "Focuses on offers, pricing, or benefits."
        - "Strong brand/marketing voice."

    message:
      definition: "Direct human-to-human or small-group communication."
      includes:
        - personal_emails
        - small_group_threads
        - work_or_collab threads between individuals
      excludes:
        - listserv blasts
        - automated notifications
        - newsletters or marketing
      signals:
        - "You could plausibly reply and expect a human response."
        - "Written by a specific person, not a system or brand."
        - "Content is relational, not just transactional."

    receipt:
      definition: "Documentation of completed money movement or completed purchase-lifecycle events."
      includes:
        # Completed financial transactions
        - payment_receipts           # "Your payment of $X was successful"
        - donation_receipts
        - refund_processed           # "Your refund has been processed"
        - charge_confirmations       # "You were charged $X"
        - ride_share_receipts
        - food_delivery_receipts
        - ecommerce_payment_receipts
        # Purchase lifecycle (logistical states)
        - order_confirmations        # "Your order #123 has been placed"
        - shipping_updates           # "Your order has shipped"
        - delivery_status            # "Out for delivery", "Delivered"
        - return_processing          # "We received your return"
      excludes:
        # These look financial but are NOT receipts (they're notifications)
        - bill_ready_notices         # "Your Verizon bill is ready" → notification
        - statement_ready_notices    # "Your statement is available" → notification
        - unpaid_invoices            # "Invoice due" → notification
        - payment_due_notices        # "Payment due by X" → notification
        - failed_payment_alerts      # "Payment failed" → notification
        - overdraft_transfers        # "We transferred to cover..." → notification (risk alert)
        - subscription_cancellation_warnings
        - autopay_enabled            # "You've turned on AutoPay" → notification (settings change)
        - autopay_scheduled          # "Your AutoPay is set for Nov 12" → notification (future payment)
        - credit_card_payment_scheduled  # "Automatic payment scheduled" → notification
      signals:
        - "Money has already moved (charge, refund, payment complete)."
        - "Tracks the lifecycle of a purchase from order to delivery."
        - "Often includes order numbers, tracking info, or itemized charges."
        - "NOT about money you OWE or WILL PAY — that's a notification."
      notes:
        - "Key distinction: completed transactions vs. pending/scheduled obligations."
        - "If the email is asking you to pay or alerting you to a bill, it's a notification."
        - "ALL AutoPay emails are notifications (settings changes, not completed transactions)."
        - "AutoPay enabled, AutoPay scheduled → notification/routine/everything-else."

    otp:
      definition: "One-time passcodes, verification codes, and 2FA codes for login or account access."
      includes:
        - login_verification_codes
        - two_factor_authentication_codes
        - account_verification_codes
        - password_reset_codes
        - sign_in_codes
      excludes:
        - password_reset_links_without_codes
        - general_security_alerts
        - fraud_alerts
      signals:
        - "Contains a numeric or alphanumeric code to enter."
        - "Subject often includes 'code', 'verify', 'OTP', or similar."
        - "Expires within minutes."

    other:
      definition: "Only used when a message clearly does not fit any other category."
      includes:
        - highly_unusual_system_emails
        - corrupted_or_empty_emails
        - edge_cases_where_type_is_ambiguous_even_after_review

  importance:
    note: |
      This section defines T0 (intrinsic) importance — the observer-independent urgency of an email.
      T0 classification is stable regardless of when you evaluate the email.

      For the full two-stage architecture (T0 → T1 temporal decay), see:
      docs/features/T0_T1_IMPORTANCE_CLASSIFICATION.md

    critical:
      definition: "If ignored, there is real-world risk, loss, or serious consequence."
      includes:
        - fraud_alerts
        - suspicious_account_activity
        - compromised_password_or_login_attempts
        - urgent_bank_issues
        - critical_insurance_or_healthcare_coverage_issues
        - one_time_passcodes (OTPs) for login or account access
      notes:
        - "OTPs are critical for access in the moment but may be suppressed or down-ranked in digests after a short time window."
        - "Critical does not guarantee permanent visibility; digest logic may hide expired or stale critical alerts."

    time_sensitive:
      definition: "Has a deadline, event time, or implied window for action (observer-independent, T0 classification)."
      includes:
        - calendar_events (with specific date/time)
        - deliveries (with tracking or scheduled dates)
        - appointments (with scheduled times)
        - bills_with_due_dates
        - limited_time_actions (e.g., confirm by a specific date)
        - trial_subscriptions          # Trials have end dates, user should decide before charged
        - support_threads              # Someone is waiting for a response
        - job_interview_offers         # Opportunity windows close quickly
        - medical_claims_threads       # Healthcare typically has response windows
        - card_activation_reminders    # Cards have implied activation windows, consequences if not activated
        - mfa_registration_reminders   # Security tokens timeout
        - budget_alerts                # May warrant user intervention while relevant
        - bill_increase_alerts         # User may want to act before next charge
        - travel_bookings              # Tied to specific travel dates
        - host_messages_for_bookings   # Airbnb/hotel hosts expect timely responses
      excludes:
        - low-impact newsletters and promos
        - OTPs (classified as critical even though they have tiny windows)
        - completed_transactions (no action needed)
      signals:
        - "Email contains or implies a specific deadline or event time."
        - "Missing the deadline would cause mild or moderate annoyance."
        - "Someone is waiting for a response (support, hosts, interviewers)."
        - "There's an implied window even if not explicitly stated (trials, card activations)."
        - "Consequences exist for inaction (overdraft, missed opportunity, service disruption)."
      notes:
        - "T0 classification does NOT consider current time — that's T1 (temporal decay)."
        - "An event 2 weeks from now is still time_sensitive (T0), even though it's not urgent today."
        - "Implied deadlines count: job offers, trial expirations, card activations have real windows."
        - "Support threads are time_sensitive because someone is waiting - responsiveness matters."

    routine:
      definition: "Low-consequence, informational, or archival content with no deadline."
      includes:
        - newsletters
        - promos
        - order_confirmations (without urgent actions)
        - payment_receipts
        - most community announcements
        - non-urgent updates
      signals:
        - "Nothing truly bad happens if you read this later or never."
        - "No specific deadline or event time."

  client_label:
    action-required:
      definition: "The user must take an action to avoid a negative consequence or to complete something important."
      includes:
        - failed_payments_declined_transactions
        - subscription_cancellation_warnings
        - service_interruption_notices
        - missing_documents_or_profile_completion_for_services
        - flight_notifications         # Check-in required, preparation needed
        - trip_reminders               # Travel preparation actions
        - security_access_reviews      # "You allowed X access" implies review/approval
        - account_compromise_alerts    # "You're one of X people pwned" - change passwords
        - card_activation_reminders    # User must activate to use the card
        - permit_application_windows   # Application deadlines
      excludes:
        - verification_codes_otps (ephemeral, go to everything-else)
        - identity_verification_requests (ephemeral, go to everything-else)
        - "was_this_you" security alerts (informational, go to everything-else unless compromised)
      signals:
        - "If you never act, something you care about may break, be blocked, or be at risk."
        - "Travel-related: check-in, preparation, or documentation needed."
        - "Security: account may be compromised and needs password changes."
      notes:
        - "Flight/trip notifications default to action-required because users need to check-in or prepare."
        - "Security access grants ('You allowed MailQ access') imply user should review for approval."
        - "Data breach notifications ('you were pwned') require password changes."

    receipts:
      definition: "All emails related to completed purchases and purchase logistics."
      includes:
        - payment_receipts             # "Your payment was successful"
        - refund_processed             # "Your refund has been processed"
        - order_confirmations          # "Your order has been placed"
        - shipping_updates             # "Your order has shipped"
        - out_for_delivery
        - delivered_notifications
        - return_received / refund_processing
        - autopay_confirmations        # "You've turned on AutoPay" (setup complete)
      excludes:
        # These are obligations, not receipts (they go to everything-else or action-required)
        - bill_ready_notices           # → notification → everything-else
        - statement_ready_notices      # → notification → everything-else
        - invoice_notices              # → notification → everything-else (if unpaid)
        - overdraft_transfers          # → notification → action-required (critical)
        - payment_due_notices          # → notification → action-required
        - payment_failed_alerts        # → notification → action-required
      notes:
        - "TYPE=receipt means completed transaction or purchase lifecycle."
        - "Billing obligations (bills, statements, invoices) are TYPE=notification."
        - "This keeps 'receipts' bucket clean: only things you've bought/paid."

    messages:
      definition: "Personal or conversational threads with real humans."
      includes:
        - one_to_one_emails
        - small_group_threads
        - conversational_replies
      notes:
        - "Some listserv or group emails MAY be labeled messages if they function as active group discussion rather than broadcast."

    everything-else:
      definition: "All remaining emails that don't fit the other UI buckets."
      includes:
        - notifications not about purchases
        - newsletters
        - promotions
        - events (where not more appropriately labeled as receipts or messages)
        - community_announcements
      notes:
        - "This is the default bucket when in doubt."
        - "The digest and ranking layers control how much of 'everything-else' you actually see."

  temporality:
    definition: "Structured representation of when something happens or is due (for events and deadlines), not just when the email was sent."
    fields:
      temporal_start: "ISO 8601 datetime or null"
      temporal_end: "ISO 8601 datetime or null"
    rules:
      extract_only_if:
        - "A real date/time for a FUTURE or upcoming event, deadline, or action appears in the subject OR snippet."
        - "The time window clearly matters for attending, joining, or acting (e.g., class tomorrow at 7pm, payment due by Friday)."
      ignore_if:
        - "The date describes when something ALREADY happened (past receipts, past deliveries, past appointments)."
        - "The date is only the email's sent/received timestamp."
        - "The date window is for shipping or delivery ranges (use importance + internal decay instead)."
        - "OTP expiration windows ('code expires in 10 minutes')."
        - "The date only appears deep in the body and not in subject/snippet (for MVP)."
    usage:
      - "Determining TODAY vs COMING UP sections in the digest."
      - "Allowing post-event decay once temporal_end is in the past."
      - "Helping de-duplicate or collapse multiple event-related emails."

  otp_rules:
    definition: "Special handling for one-time passcodes."
    classification:
      type: otp
      importance: critical
      client_label: everything-else
      temporality:
        temporal_start: null
        temporal_end: null
    digest_behavior:
      - "OTPs are critical in the moment but usually have no ongoing digest value."
      - "They may be excluded entirely from digests, or shown only very briefly if they are extremely recent."
      - "Expiration windows are NOT encoded as temporality; decay is handled by separate business rules."

  listserv:
    definition: "Emails sent to a group/list address where you are a subscriber."
    classification_strategy: "Classify by content, not by sender or the fact that it is a listserv."
    examples:
      - name: "Downtown Dharma event announcement"
        classification:
          type: event
          importance: time_sensitive  # T0: event has a date/time (observer-independent)
          client_label: everything-else
      - name: "Downtown Dharma teaching / reflection"
        classification:
          type: newsletter
          importance: routine
          client_label: everything-else
      - name: "Downtown Dharma discussion thread between members"
        classification:
          type: message
          importance: routine
          client_label: messages
    notes:
      - "Do not create a separate TYPE for listserv."
      - "Use the same decision tree as all other emails; just be aware that sender is a group."

  order_lifecycle:
    definition: "How to classify and label purchase-related emails across their lifecycle."
    principle: |
      Time-sensitive only when there's an ACTION WINDOW or DEADLINE.
      Most delivery lifecycle emails are informational - no user action changes the outcome.
    mapping:
      order_confirmation:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Order is placed, no action needed."
      processing:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Still being prepared."
      shipped:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Package left warehouse, could be days away. No action possible."
      in_transit:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Package is moving. User can't speed it up."
      out_for_delivery:
        type: receipt
        client_label: receipts
        default_importance: time_sensitive
        reason: "ACTION WINDOW: User may need to be home, clear porch, or watch for driver."
      arriving_today:
        type: receipt
        client_label: receipts
        default_importance: time_sensitive
        reason: "ACTION WINDOW: Delivery happening within hours."
      delivered:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Already happened. User retrieves at their convenience."
      delivery_attempted:
        type: receipt
        client_label: receipts
        default_importance: time_sensitive
        reason: "ACTION REQUIRED: User must reschedule or pick up."
      held_at_facility:
        type: receipt
        client_label: receipts
        default_importance: time_sensitive
        reason: "DEADLINE: Must pick up by X date or package is returned."
      delivery_exception:
        type: receipt
        client_label: receipts
        default_importance: time_sensitive
        reason: "ACTION REQUIRED: Address issue, contact carrier, etc."
      return_initiated_or_received:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Return is processing."
      refund_processed:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Money is on its way back."
      payment_receipt:
        type: receipt
        client_label: receipts
        default_importance: routine
        reason: "Informational. Transaction complete."
    time_sensitive_criteria:
      - "There is an ACTION WINDOW (be home, clear porch, sign for package)"
      - "There is a DEADLINE (pick up by X date, will be returned)"
      - "User action can change the outcome"
    routine_criteria:
      - "Purely informational - user can't change anything"
      - "Event already happened (delivered, refunded)"
      - "Event is far in the future (shipped, in transit)"
    notes:
      - "All purchase-related emails are TYPE=receipt and live in the receipts UI bucket."
      - "Temporality is generally NOT extracted for shipping/delivery dates; recency and decay handle relevance."
      - "'Shipped' is NEVER time_sensitive - it's just 'left the warehouse', could be days away."
      - "'Delivered' is NEVER time_sensitive - it already happened, retrieve at your convenience."

  billing_notifications:
    definition: "Financial emails describing upcoming, pending, or overdue obligations (NOT completed money movement)."
    type: notification
    includes:
      - bill_ready                   # "Your Verizon bill is ready"
      - statement_ready              # "Your statement is available"
      - payment_due                  # "Payment due by Nov 15"
      - invoice_notice               # "Invoice for October" (if unpaid)
      - unpaid_invoice               # "Your invoice is past due"
      - subscription_payment_failed  # "Your subscription payment failed"
      - credit_card_payment_failed   # "Payment declined"
      - overdraft_transfer           # "We transferred money to cover..." (risk signal)
      - delinquency_notices          # "Your account is past due"
      - autopay_enabled              # "You've turned on AutoPay" (settings change)
      - autopay_scheduled            # "Your AutoPay is set for Nov 12" (future payment)
      - credit_card_payment_scheduled  # "Automatic payment scheduled"
    excludes:
      - payment_receipts             # "Payment successful" → receipt
      - refund_processed             # "Refund complete" → receipt
    importance_rules:
      bill_ready: routine            # Informational, no immediate action
      statement_ready: routine       # Informational
      unpaid_invoice: routine        # Needs attention but not urgent
      autopay_enabled: routine       # Settings change, informational
      autopay_scheduled: routine     # Informational reminder about future payment
      payment_due: time_sensitive    # Has a deadline
      subscription_payment_failed: time_sensitive  # Needs resolution
      credit_card_payment_failed: critical         # Financial risk
      overdraft_transfer: critical   # Financial risk signal
    client_label_rules:
      bill_ready: everything-else
      statement_ready: everything-else
      autopay_enabled: everything-else
      autopay_scheduled: everything-else
      payment_due: action-required
      unpaid_invoice: action-required
      subscription_payment_failed: action-required
      credit_card_payment_failed: action-required
      overdraft_transfer: action-required
    notes:
      - "These are obligations, not completed transactions."
      - "Users need to see these but they don't belong in the 'receipts' bucket."
      - "Critical items (payment failures, overdrafts) go to action-required."
      - "Routine items (bill ready, statement available) go to everything-else."

  decision_tree:
    - step: 1
      question: "Is this a one-time passcode, verification code, or 2FA code?"
      if_yes:
        type: otp
      if_no: next

    - step: 2
      question: "Is this about attending something at a specific date/time (event, class, meetup, service, call)?"
      if_yes:
        type: event
      if_no: next

    - step: 3
      question: "Is this about a completed purchase, order, shipping, delivery, or completed payment?"
      notes: "Money has already moved OR purchase logistics (order placed, shipped, delivered, refunded)"
      if_yes:
        type: receipt
      if_no: next

    - step: 3a
      question: "Is this about an unpaid bill, statement, invoice, payment due, or financial obligation?"
      notes: "Bills ready, statements available, payment due, payment failed, overdraft alerts"
      if_yes:
        type: notification
      if_no: next

    - step: 4
      question: "Is this primarily updating you about an account, security, or system status?"
      if_yes:
        type: notification
      if_no: next

    - step: 5
      question: "Is this primarily trying to sell or market a product, service, or experience?"
      if_yes:
        type: promotion
      if_no: next

    - step: 6
      question: "Is this editorial / informational content you might read like an article or update?"
      if_yes:
        type: newsletter
      if_no: next

    - step: 7
      question: "Is this a direct conversation with a real person or small group?"
      if_yes:
        type: message
      if_no:
        type: other

    notes:
      - "Step 3 (receipt) captures COMPLETED transactions and purchase logistics."
      - "Step 3a (notification) captures UNPAID obligations (bills, statements, invoices)."
      - "Key signals for receipt: 'shipped', 'delivered', 'order', 'refund', 'payment successful'."
      - "Key signals for billing notification: 'bill ready', 'statement', 'invoice', 'payment due', 'overdraft'."
      - "Notification also covers account/security updates (step 4)."
```
