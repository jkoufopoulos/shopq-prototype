/**
 * Test what different Gmail queries return
 *
 * STEP 1: Get your OAuth token by running this first:
 * chrome.runtime.sendMessage({action: 'getToken'}, token => console.log('TOKEN:', token));
 *
 * STEP 2: Copy the token and paste it below where it says YOUR_TOKEN_HERE
 *
 * STEP 3: Run this script
 */

(async function testInboxQueries() {
  console.clear();
  console.log('🔍 Testing Gmail Query Behavior\n');

  // Paste your token here (get it from step 1 above)
  const token = 'YOUR_TOKEN_HERE';

  if (token === 'YOUR_TOKEN_HERE') {
    console.error('❌ Please run step 1 first to get your token, then paste it in the script');
    return;
  }

  const queries = [
    'in:inbox',
    'is:inbox',
    'label:inbox',
    'label:INBOX',
    'newer_than:7d',
    'newer_than:7d in:inbox',
  ];

  console.log('='.repeat(60));
  for (const query of queries) {
    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/threads?q=${encodeURIComponent(query)}&maxResults=100`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    const data = await response.json();
    const count = data.threads?.length || 0;
    console.log(`"${query.padEnd(25)}" → ${count} threads`);
  }
  console.log('='.repeat(60));

  console.log('\n💡 Now try these searches manually in Gmail UI:');
  console.log('   1. in:inbox');
  console.log('   2. is:inbox');
  console.log('   3. (no search - just look at default inbox view)');
  console.log('\n   Compare the counts you see vs what the API returned above');
})();
