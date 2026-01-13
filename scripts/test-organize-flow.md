# Email Organization Testing Guide

## Current Status
✅ **Fix Applied**: Changed from `messages.modify` to `threads.modify` in `extension/modules/gmail.js:629`

## Why This Fix Works
- **Problem**: Using `messages/${id}/modify` only labels ONE message in a thread
- **Impact**: Multi-message threads don't show labels in inbox view (Gmail shows thread-level labels)
- **Solution**: Using `threads/${threadId}/modify` labels the ENTIRE thread atomically
- **Result**: All emails in thread get labeled AND archived together

## Test Procedure

### Step 1: Reload Extension
1. Open `chrome://extensions`
2. Find "ShopQ" extension
3. Click the reload icon (🔄)
4. Verify: No error messages appear

### Step 2: Open Gmail & DevTools
1. Navigate to `https://mail.google.com/mail/u/0/#inbox`
2. Press `F12` to open DevTools
3. Click "Console" tab
4. Clear console (click 🚫 icon or Cmd+K)

### Step 3: Trigger Organization
In the console, run:
```javascript
triggerAutoOrganizeNow()
```

### Step 4: Watch Console Output

**Expected Success Indicators:**
```
🔔 Auto-organize alarm triggered
🚀 Running automatic inbox organization...
📬 Found X unlabeled emails to process
🏷️ Classifying X emails...
✅ Classification results received
🔧 [DEBUG] Modifying thread <threadId>: {"addLabelIds":[...],"removeLabelIds":["INBOX","UNREAD","IMPORTANT"]}
✅ Labels applied successfully
✅ Auto-organize complete: X emails processed, 0 remaining
```

**Key Things to Check:**
- ✅ Every email shows "🔧 [DEBUG] Modifying thread XXX"
- ✅ Each shows `addLabelIds` with ShopQ label IDs
- ✅ Each shows `removeLabelIds: ["INBOX","UNREAD","IMPORTANT"]`
- ✅ Final message says "0 remaining"
- ✅ No errors like "❌ Failed to fetch thread" or "⚠️ No labels for email"

### Step 5: Verify Inbox
1. Look at Gmail inbox
2. **Expected**: Inbox count should be 0
3. **If not**: Check console for errors

### Step 6: Verify Labels Applied
1. Click "All Mail" in Gmail sidebar
2. In search box, type: `label:ShopQ-*`
3. Press Enter
4. **Expected**: All recently organized emails appear with ShopQ labels visible
5. Click on a few emails - each should show 1-2 ShopQ labels

### Step 7: Verify Taskrabbit Email
1. In "All Mail", search for: `from:taskrabbit`
2. Find the "Your upcoming General Mounting task" email
3. **Expected**: Should have ShopQ labels (likely ShopQ-Events or ShopQ-Notifications)
4. **Expected**: Should NOT be in inbox

### Step 8: Verify Digest
1. In "All Mail", look for the digest email (subject starts with "Your Inbox --")
2. Open it
3. **Expected**: All organized emails should be mentioned in the digest
4. **Expected**: Each entity should have a clickable number (1), (2), etc.
5. Click a few numbers - should jump to corresponding email in Gmail

## Troubleshooting

### Issue: Emails still in inbox
**Check console for:**
- "❌ Gmail API error" → Possible auth issue or API rate limit
- "removeLabelIds: []" → Archive flag not being set

**Fix:**
- Verify line 621 in gmail.js has: `removeLabelIds: removeFromInbox ? ['INBOX', 'UNREAD', 'IMPORTANT'] : []`
- Check that `applyLabels()` is called with third parameter `true`

### Issue: No labels on some emails
**Check console for:**
- "⚠️ No labels for email: <id>" → Classification returned empty labels
- "❌ Failed to fetch thread" → Gmail API error

**Debug:**
- Look for classification results in console
- Check if backend API is running on localhost:8000
- Try: `curl http://localhost:8000/health`

### Issue: Taskrabbit email specifically missing labels
**This was the bug we just fixed!**
- Taskrabbit emails are likely multi-message threads
- Old code: `messages/${id}/modify` only labeled first message
- New code: `threads/${threadId}/modify` labels entire thread
- **Solution**: Extension must be reloaded to pick up the fix

### Issue: Digest missing some emails
**Check:**
- Console logs for entity extraction
- Look for "Extracted X entities from Y emails"
- Verify emails were classified as "critical" or "time-sensitive" (routine emails don't get entities)

## Acceptance Criteria (User Requirements)

✅ **Every email has an appropriate label (1-2 labels max)**
- Check: All emails in "label:ShopQ-*" search have visible labels
- Check: No emails have more than 2 ShopQ labels

✅ **Every email is archived**
- Check: Inbox count is 0
- Check: All emails moved to "All Mail"

✅ **No emails in inbox**
- Check: Gmail inbox shows "No new mail!"

✅ **Every organized email is input to digest**
- Check: Digest contains all critical/time-sensitive emails
- Check: Each has a clickable reference number

## Success Criteria

If all of the above pass, the fix is complete! 🎉

Next steps would be:
1. Monitor for any edge cases over next few days
2. Consider adding automated tests for this flow
3. Document the threads.modify vs messages.modify distinction
