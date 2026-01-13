# Debug: Check What Label IDs Map To

Run this in Gmail DevTools Console (F12) while looking at your inbox:

```javascript
// Get OAuth token from extension
chrome.runtime.sendMessage({action: 'getToken'}, async (token) => {
  console.log('🔍 Checking label IDs...\n');

  // These are the label IDs from your logs
  const suspectLabelIds = [
    'Label_223', 'Label_224', 'Label_225', 'Label_226',
    'Label_227', 'Label_228', 'Label_229', 'Label_230',
    'Label_231', 'Label_233', 'Label_234', 'Label_235'
  ];

  for (const labelId of suspectLabelIds) {
    try {
      const response = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/labels/${labelId}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const label = await response.json();
        const isMailQ = label.name && label.name.startsWith('MailQ');
        console.log(`${isMailQ ? '✅' : '❌'} ${labelId} → "${label.name}"`);
      } else {
        console.log(`⚠️ ${labelId} → Failed to fetch (${response.status})`);
      }
    } catch (error) {
      console.log(`❌ ${labelId} → Error: ${error.message}`);
    }
  }
});
```

**This will show you what those Label_XXX IDs actually are.**

If they're MailQ labels → Extension is working correctly (just confusing label IDs)
If they're NOT MailQ labels → Extension has a bug in label checking logic
