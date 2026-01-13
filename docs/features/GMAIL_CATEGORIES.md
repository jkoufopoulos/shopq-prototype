# Gmail Category Labels - Important Behavior

## Issue
Emails in Gmail's category tabs (Updates, Promotions, Social, Forums) do **NOT** have the `INBOX` label. They only have category labels like:
- `CATEGORY_UPDATES`
- `CATEGORY_PROMOTIONS`
- `CATEGORY_SOCIAL`
- `CATEGORY_FORUMS`

This means the query `in:inbox` will **exclude** all emails in category tabs, even though they appear in the inbox visually.

## Example
Hertz email "Your rental return is coming up!" (October 11):
- Message ID: `199d41a7fd4ab269`
- Labels: `['CATEGORY_UPDATES']`
- Has INBOX label: `false`
- Appears in inbox visually: `true`

## Solution
Updated query in `extension/modules/gmail.js`:

**Before:**
```
in:inbox -label:ShopQ/*
```

**After:**
```
(in:inbox OR category:updates OR category:promotions OR category:social OR category:forums) -in:trash -in:spam -label:ShopQ/*
```

This ensures we capture:
1. Primary inbox emails (have `INBOX` label)
2. Category tab emails (have `CATEGORY_*` labels)
3. Exclude trash, spam, and already-labeled ShopQ emails

## Gmail Category Documentation
- Primary: Has `INBOX` label, no category label
- Updates: Has `CATEGORY_UPDATES`, no `INBOX` label
- Promotions: Has `CATEGORY_PROMOTIONS`, no `INBOX` label
- Social: Has `CATEGORY_SOCIAL`, no `INBOX` label
- Forums: Has `CATEGORY_FORUMS`, no `INBOX` label

## Impact
Without this fix, ShopQ would only organize emails in the Primary tab, missing potentially 50%+ of inbox emails that are in category tabs.
