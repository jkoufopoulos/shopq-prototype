/**
 * Run this in Gmail console to diagnose label issue
 *
 * This will:
 * 1. Fetch one of your "Your Inbox" emails
 * 2. Check what labels Gmail API says it has
 * 3. Look up what those label IDs actually are
 * 4. Compare with what's visible in UI
 */

(async function diagnoseLabelIssue() {
  console.clear();
  console.log('🔍 Diagnosing Label Issue\n' + '='.repeat(60));

  // Get auth token
  const getToken = () => new Promise((resolve) => {
    chrome.runtime.sendMessage({action: 'getToken'}, resolve);
  });

  const token = await getToken();
  if (!token) {
    console.error('❌ Could not get OAuth token');
    return;
  }

  console.log('✅ Got OAuth token\n');

  // Fetch recent emails
  console.log('📧 Fetching inbox emails...');
  const searchResponse = await fetch(
    'https://gmail.googleapis.com/gmail/v1/users/me/messages?q=newer_than:3d&maxResults=50',
    { headers: { 'Authorization': `Bearer ${token}` } }
  );

  const searchData = await searchResponse.json();
  console.log(`Found ${searchData.messages?.length || 0} messages\n`);

  if (!searchData.messages || searchData.messages.length === 0) {
    console.error('❌ No messages found');
    return;
  }

  // Check first 5 emails
  console.log('🔍 Checking first 5 emails for label discrepancy...\n');

  for (let i = 0; i < Math.min(5, searchData.messages.length); i++) {
    const msgId = searchData.messages[i].id;

    // Fetch full message
    const msgResponse = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msgId}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    const msg = await msgResponse.json();
    const subject = msg.payload.headers.find(h => h.name === 'Subject')?.value || 'No subject';
    const labelIds = msg.labelIds || [];

    console.log(`\n📧 Email ${i + 1}: "${subject.substring(0, 60)}..."`);
    console.log(`   Label IDs: ${labelIds.join(', ')}`);

    // Look up each label ID
    const labelNames = [];
    for (const labelId of labelIds) {
      try {
        const labelResponse = await fetch(
          `https://gmail.googleapis.com/gmail/v1/users/me/labels/${labelId}`,
          { headers: { 'Authorization': `Bearer ${token}` } }
        );

        if (labelResponse.ok) {
          const label = await labelResponse.json();
          labelNames.push(label.name);

          if (label.name.startsWith('MailQ')) {
            console.log(`   ✅ ${labelId} → "${label.name}" (MailQ label)`);
          } else {
            console.log(`   ➖ ${labelId} → "${label.name}"`);
          }
        }
      } catch (error) {
        console.log(`   ❌ ${labelId} → Error fetching`);
      }
    }

    const hasMailQInAPI = labelNames.some(name => name.startsWith('MailQ'));
    console.log(`   API says has MailQ: ${hasMailQInAPI ? 'YES' : 'NO'}`);
    console.log(`   (Check Gmail UI: does this email show MailQ labels?)`);
  }

  console.log('\n' + '='.repeat(60));
  console.log('💡 DIAGNOSIS:');
  console.log('   If API says "has MailQ: YES" but UI shows NO labels');
  console.log('   → Gmail API data is stale or out of sync');
  console.log('   → Extension is using API data (thinks labeled)');
  console.log('   → But emails are actually unlabeled');
  console.log('\n   SOLUTION: Extension should not trust labelIds from API');
  console.log('   → Use search query "-label:MailQ/*" instead');
})();
