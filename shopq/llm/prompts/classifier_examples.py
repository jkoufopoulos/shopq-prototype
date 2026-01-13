"""
Static few-shot examples for email classifier training.

These examples teach the LLM:
1. What output format to use (JSON with specific fields)
2. How to classify different email types
3. When to use high vs low confidence scores
4. Edge cases and ambiguous classifications

NOTE: domains and domain_conf fields removed - deprecated in current taxonomy.
Classification now uses: type, importance, attention only.
"""

STATIC_FEWSHOT_EXAMPLES = """FEW-SHOT EXAMPLES (Learn from these):

Example 1 - Shopping Receipt:
From: auto-confirm@amazon.com
Subject: Order Confirmation
Snippet: Thank you for your order. Your order #123-456 will arrive...
{{
  "type": "receipt",
  "type_conf": 0.95,
  "importance": "routine",
  "importance_conf": 0.95,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

Example 2 - Shipping Update (Order Lifecycle = Receipt):
From: shipment-tracking@amazon.com
Subject: Your package has shipped
Snippet: Your order is on the way. Track your package...
{{
  "type": "receipt",
  "type_conf": 0.92,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: Shipping updates are type=receipt (order lifecycle), NOT notification

Example 3 - Finance Statement (Billing Obligation = Notification):
From: statements@schwab.com
Subject: Your September statement is ready
Snippet: Your monthly account statement is now available...
{{
  "type": "notification",
  "type_conf": 0.94,
  "importance": "routine",
  "importance_conf": 0.95,
  "attention": "none",
  "attention_conf": 0.92,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: Statement ready = billing obligation = type=notification (NOT receipt)
# Receipt = money already moved. Statement = document available, no transaction.

Example 3b - AutoPay Scheduled (Billing Obligation = Notification):
From: affirm-billing@shop.affirm.com
Subject: Your AutoPay is set for Nov 12, 2025
Snippet: A payment is coming up... You'll pay $92.08 on Nov 12
{{
  "type": "notification",
  "type_conf": 0.93,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.92,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: AutoPay scheduled = future payment = type=notification (NOT receipt)
# Receipt = money already moved. AutoPay = money will move later.

Example 3c - Bill Ready (Billing Obligation = Notification):
From: verizonwireless@vtext.com
Subject: Your Verizon bill is ready
Snippet: Your bill for November is available to view...
{{
  "type": "notification",
  "type_conf": 0.92,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.92,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: Bill ready = billing obligation = type=notification (NOT receipt)
# Receipt = money already moved. Bill ready = money owed, not yet paid.

Example 3d - Invoice Notice (Billing Obligation = Notification):
From: billing@heroku.com
Subject: [billing] Heroku Invoice for October
Snippet: Your invoice for October 2025 is attached...
{{
  "type": "notification",
  "type_conf": 0.94,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.92,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: Invoice = billing obligation = type=notification (NOT receipt)
# Receipt = money already moved. Invoice = request for payment.

Example 3e - Security Alert (TRUE Notification - not financial):
From: no-reply@accounts.google.com
Subject: Security alert: New sign-in from Chrome on Windows
Snippet: Someone just signed into your account from a new device...
{{
  "type": "notification",
  "type_conf": 0.95,
  "importance": "routine",
  "importance_conf": 0.85,
  "attention": "none",
  "attention_conf": 0.85,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: Security alerts are TRUE notifications (not about money)

Example 4 - Finance Receipt:
From: service@paypal.com
Subject: You sent a payment
Snippet: You sent $25.00 to John Doe...
{{
  "type": "receipt",
  "type_conf": 0.96,
  "importance": "routine",
  "importance_conf": 0.95,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

Example 5 - Job Alert (Time Sensitive):
From: jobs-listings@linkedin.com
Subject: 20 new jobs for Product Manager
Snippet: Based on your profile, here are new opportunities...
{{
  "type": "notification",
  "type_conf": 0.90,
  "importance": "time_sensitive",
  "importance_conf": 0.85,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.85
}}
# NOTE: Job alerts are time_sensitive (opportunities have limited windows)

Example 6 - Newsletter (Content):
From: newsletter@lennysnewsletter.com
Subject: OpenAI Product Leader: The 7-Step Playbook
Snippet: This week's essay on product leadership...
{{
  "type": "newsletter",
  "type_conf": 0.94,
  "importance": "routine",
  "importance_conf": 0.95,
  "attention": "none",
  "attention_conf": 0.98,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

Example 7 - Event (Shows):
From: events@elsewhere.com
Subject: New shows this week at Elsewhere
Snippet: This week's lineup: Friday 8pm - DJ Night, Saturday 9pm...
{{
  "type": "event",
  "type_conf": 0.92,
  "importance": "time_sensitive",
  "importance_conf": 0.85,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.85
}}

Example 8 - Calendar Event:
From: calendar-notification@google.com
Subject: Notification: J & V Catch-up @ Fri Oct 18
Snippet: Reminder: Meeting with Julia at 6pm...
{{
  "type": "event",
  "type_conf": 0.95,
  "importance": "time_sensitive",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.90,
  "relationship": "from_unknown",
  "relationship_conf": 0.80
}}

Example 9 - Promotion:
From: marketing@hertz.com
Subject: Upgrade today with Hertz
Snippet: Exclusive offer: Upgrade to a premium vehicle...
{{
  "type": "promotion",
  "type_conf": 0.93,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.98,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

Example 10 - Message (Action Required):
From: jane@permitflow.com
Subject: Re: Product @ PermitFlow (Kleiner Perkins backed)
Snippet: Hi Justin, Following up on our conversation. Can you review...
{{
  "type": "message",
  "type_conf": 0.94,
  "importance": "time_sensitive",
  "importance_conf": 0.85,
  "attention": "action_required",
  "attention_conf": 0.85,
  "relationship": "from_known_person",
  "relationship_conf": 0.80
}}

Example 11 - Finance Alert (Critical):
From: alerts@vanguard.com
Subject: ⚠️ Account balance alert
Snippet: Your account balance has fallen below your specified threshold...
{{
  "type": "notification",
  "type_conf": 0.93,
  "importance": "critical",
  "importance_conf": 0.90,
  "attention": "action_required",
  "attention_conf": 0.90,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

Example 12 - Generic Newsletter:
From: newsletter@morningbrew.com
Subject: 💡🧠 The curious case of smell
Snippet: Today's edition: The science of smell and memory...
{{
  "type": "newsletter",
  "type_conf": 0.95,
  "importance": "routine",
  "importance_conf": 0.95,
  "attention": "none",
  "attention_conf": 0.98,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}

Example 13 - OTP Verification Code (Critical):
From: noreply@github.com
Subject: [GitHub] Your verification code
Snippet: Your verification code is 123456. This code expires in 10 minutes...
{{
  "type": "otp",
  "type_conf": 0.99,
  "importance": "critical",
  "importance_conf": 0.99,
  "attention": "action_required",
  "attention_conf": 0.99,
  "relationship": "from_unknown",
  "relationship_conf": 0.95
}}

Example 14 - AMBIGUOUS: Could be newsletter OR promotion (LOW CONFIDENCE):
From: deals@retailer.com
Subject: This week's top picks for you
Snippet: We thought you'd love these items based on your browsing history...
{{
  "type": "promotion",
  "type_conf": 0.75,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: "top picks" + "browsing history" suggests promotion, but could also be
# a curated newsletter. Only 1 weak signal (personalization), so type_conf=0.75

Example 15 - AMBIGUOUS: Message vs notification (LOW CONFIDENCE):
From: no-reply@service.com
Subject: Quick update on your request
Snippet: We wanted to let you know that your submission has been received...
{{
  "type": "notification",
  "type_conf": 0.72,
  "importance": "routine",
  "importance_conf": 0.85,
  "attention": "none",
  "attention_conf": 0.90,
  "relationship": "from_unknown",
  "relationship_conf": 0.85
}}
# NOTE: "no-reply" suggests notification (automated), but "quick update" could
# be a human follow-up. Low signals = type_conf=0.72

Example 16 - AMBIGUOUS: Receipt vs notification (MEDIUM CONFIDENCE):
From: billing@company.com
Subject: Payment received - thank you!
Snippet: We've received your payment. Your account is now current.
{{
  "type": "receipt",
  "type_conf": 0.82,
  "importance": "routine",
  "importance_conf": 0.90,
  "attention": "none",
  "attention_conf": 0.95,
  "relationship": "from_unknown",
  "relationship_conf": 0.90
}}
# NOTE: "Payment received" confirms money moved (=receipt), but lacks order #
# or specific amount. Strong signal but not definitive = type_conf=0.82

"""
