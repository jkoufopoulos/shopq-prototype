/**
 * Context Digest Module
 *
 * Generates timeline-centric context digest using entity extraction + LLM
 *
 * Features:
 * - Entity extraction (flights, events, deadlines)
 * - Importance classification (critical/time-sensitive/routine)
 * - Weather enrichment
 * - Transparent noise summary
 * - Adaptive word count
 * - <90 words, feels like "a friend recapping your day"
 */

let _cachedContextEnv = null;
let _cachedUserName = null;

/**
 * Fetch display name from Google People API
 * @returns {Promise<string|null>} First name or null if not available
 */
async function fetchDisplayNameFromGoogle() {
  try {
    // Get OAuth token (uses cached token if available)
    const token = await getAuthToken({ forceRefresh: false });
    console.log('[CONTEXT-DIGEST] Fetching user name from Google APIs...');

    // Try UserInfo API first (matches userinfo.profile scope in manifest)
    const userInfoResponse = await fetch(
      'https://www.googleapis.com/oauth2/v3/userinfo',
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    console.log(`[CONTEXT-DIGEST] UserInfo API status: ${userInfoResponse.status}`);

    if (userInfoResponse.ok) {
      const data = await userInfoResponse.json();
      console.log('[CONTEXT-DIGEST] UserInfo API data:', JSON.stringify(data));
      // UserInfo returns: { given_name: "Justin", family_name: "...", name: "Justin ..." }
      if (data.given_name) {
        console.log(`[CONTEXT-DIGEST] Got name from UserInfo API: ${data.given_name}`);
        return data.given_name;
      } else if (data.name) {
        const firstName = data.name.split(' ')[0];
        console.log(`[CONTEXT-DIGEST] Got name from UserInfo API (split): ${firstName}`);
        return firstName;
      } else {
        console.warn('[CONTEXT-DIGEST] UserInfo API returned no name fields');
      }
    } else {
      const errorText = await userInfoResponse.text();
      console.warn(`[CONTEXT-DIGEST] UserInfo API error: ${userInfoResponse.status}`, errorText);
    }

    // Fallback: Try People API (requires people.googleapis.com host permission)
    console.log('[CONTEXT-DIGEST] Trying People API fallback...');
    const peopleResponse = await fetch(
      'https://people.googleapis.com/v1/people/me?personFields=names',
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    console.log(`[CONTEXT-DIGEST] People API status: ${peopleResponse.status}`);

    if (peopleResponse.ok) {
      const data = await peopleResponse.json();
      if (data.names && data.names.length > 0) {
        const primaryName = data.names.find(n => n.metadata?.primary) || data.names[0];
        if (primaryName.givenName) {
          console.log(`[CONTEXT-DIGEST] Got name from People API: ${primaryName.givenName}`);
          return primaryName.givenName;
        } else if (primaryName.displayName) {
          const firstName = primaryName.displayName.split(' ')[0];
          console.log(`[CONTEXT-DIGEST] Got name from People API (split): ${firstName}`);
          return firstName;
        }
      }
    } else {
      const errorText = await peopleResponse.text();
      console.warn(`[CONTEXT-DIGEST] People API error: ${peopleResponse.status}`, errorText);
    }

    console.warn('[CONTEXT-DIGEST] Both Google APIs failed to return name');
    return null;
  } catch (error) {
    console.warn('[CONTEXT-DIGEST] Failed to fetch user name from Google:', error);
    return null;
  }
}

/**
 * Get user's first name for personalized greeting
 * Priority: stored custom name → Google UserInfo/People API → empty string
 */
async function getUserFirstName() {
  // Return cached value if available
  if (_cachedUserName !== null) {
    return _cachedUserName;
  }

  try {
    // Check if user has set a custom name in storage
    const stored = await chrome.storage.local.get('userName');
    if (stored.userName) {
      _cachedUserName = stored.userName;
      return _cachedUserName;
    }

    // Try Google APIs (UserInfo first, then People API as fallback)
    const firstName = await fetchDisplayNameFromGoogle();
    if (firstName && firstName.length >= 2) {
      _cachedUserName = firstName.charAt(0).toUpperCase() + firstName.slice(1).toLowerCase();
      console.log(`[CONTEXT-DIGEST] Using name: ${_cachedUserName}`);
      return _cachedUserName;
    }

    // Fallback: no name available
    console.warn('[CONTEXT-DIGEST] Could not fetch user name from Google APIs');
    _cachedUserName = '';
    return _cachedUserName;
  } catch (error) {
    console.warn('⚠️ [CONTEXT-DIGEST] Failed to get user name:', error);
    _cachedUserName = '';
    return _cachedUserName;
  }
}

async function lookupLocation() {
  try {
    const response = await fetch('https://ipapi.co/json/');
    if (!response.ok) {
      return { city: null, region: null };
    }
    const data = await response.json();
    return {
      city: data.city || null,
      region: data.region || null  // State/province for disambiguation (e.g., "New York")
    };
  } catch (error) {
    console.warn('⚠️ [CONTEXT-DIGEST] Failed to lookup location:', error);
    return { city: null, region: null };
  }
}

async function getClientContextEnv() {
  if (_cachedContextEnv) {
    return _cachedContextEnv;
  }

  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  let offsetMinutes = null;
  try {
    offsetMinutes = new Date().getTimezoneOffset();
  } catch (error) {
    console.warn('⚠️ [CONTEXT-DIGEST] Failed to read timezone offset:', error);
  }

  const location = await lookupLocation();

  _cachedContextEnv = {
    timezone,
    timezoneOffsetMinutes: Number.isFinite(offsetMinutes) ? offsetMinutes : null,
    city: location.city,
    region: location.region
  };

  console.log('[CONTEXT-DIGEST] Client environment:', _cachedContextEnv);
  return _cachedContextEnv;
}

/**
 * Generate context digest HTML using backend API
 */
async function generateContextDigestHTML(currentData) {
  try {
    const apiUrl = CONFIG.SHOPQ_API_URL;

    console.log(`🌟 [CONTEXT-DIGEST] Calling ${apiUrl}/api/context-digest`);
    console.log(`🌟 [CONTEXT-DIGEST] Sending ${currentData.length} emails`);

    const clientEnv = await getClientContextEnv();
    const clientNow = new Date().toISOString();
    const userName = await getUserFirstName();

    const response = await resilientFetch(
      `${apiUrl}/api/context-digest`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          current_data: currentData,
          timezone: clientEnv.timezone,
          timezone_offset_minutes: clientEnv.timezoneOffsetMinutes,
          client_now: clientNow,
          city: clientEnv.city,
          region: clientEnv.region,  // State/province for weather disambiguation
          user_name: userName || undefined  // Only send if available
        })
      },
      { timeoutMs: 60000, retries: 2 }  // 60s timeout, 2 retries for digest generation
    );

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();

    console.log('🌟 [CONTEXT-DIGEST] Response received:');
    console.log('   Subject:', result.subject);
    console.log('   Metadata:', result.metadata);

    // Fetch and display tracking report if session_id is available
    if (result.metadata && result.metadata.session_id) {
      await displayTrackingReport(result.metadata.session_id);
    }

    return result;  // { html, subject, metadata }

  } catch (error) {
    console.error('❌ [CONTEXT-DIGEST] Failed to generate:', error);
    throw error;
  }
}

/**
 * Fetch and display tracking report for a session
 */
async function displayTrackingReport(sessionId) {
  try {
    const apiUrl = CONFIG.SHOPQ_API_URL;
    const response = await fetch(`${apiUrl}/api/tracking/session/${sessionId}`);

    if (!response.ok) {
      console.warn(`⚠️ Could not fetch tracking report for session ${sessionId}`);
      return;
    }

    const data = await response.json();
    const summary = data.summary;
    const threads = data.threads;

    console.log('\n' + '='.repeat(80));
    console.log('📊 MAILQ SESSION REPORT');
    console.log('='.repeat(80));
    console.log(`\n📋 Session: ${sessionId}`);

    // Classification stats (most useful for prompt tuning)
    if (summary.classification) {
      console.log(`\n🤖 CLASSIFICATION (this session)`);
      console.log(`  Total: ${summary.total_threads} emails`);
      console.log(`  Avg Confidence: ${(summary.classification.avg_confidence * 100).toFixed(1)}%`);

      console.log(`\n  Decider Breakdown:`);
      const deciders = summary.classification.decider_breakdown || {};
      Object.entries(deciders)
        .sort((a, b) => b[1] - a[1])
        .forEach(([decider, count]) => {
          const pct = ((count / summary.total_threads) * 100).toFixed(1);
          console.log(`    ${decider}: ${count} (${pct}%)`);
        });

      console.log(`\n  Type Breakdown:`);
      const types = summary.classification.type_breakdown || {};
      Object.entries(types)
        .sort((a, b) => b[1] - a[1])
        .forEach(([type, count]) => {
          const pct = ((count / summary.total_threads) * 100).toFixed(1);
          console.log(`    ${type}: ${count} (${pct}%)`);
        });
    }

    console.log(`\n📈 IMPORTANCE`);
    console.log(`  Critical: ${summary.importance.critical}`);
    console.log(`  Time-sensitive: ${summary.importance.time_sensitive}`);
    console.log(`  Routine: ${summary.importance.routine}`);
    console.log(`  Verifier used: ${summary.verified_count}/${summary.total_threads}`);

    console.log(`\n🎯 DIGEST`);
    console.log(`  Featured: ${summary.digest_breakdown.featured}`);
    console.log(`  Orphaned: ${summary.digest_breakdown.orphaned}`);
    console.log(`  Noise: ${summary.digest_breakdown.noise}`);
    console.log(`  Entities: ${summary.entities_extracted}/${summary.total_threads}`);

    // Show importance reasons
    const reasonCounts = {};
    threads.forEach(t => {
      const key = `${t.importance}: ${t.importance_reason}`;
      reasonCounts[key] = (reasonCounts[key] || 0) + 1;
    });

    console.log(`\n💡 IMPORTANCE REASONS`);
    Object.entries(reasonCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .forEach(([reason, count]) => {
        console.log(`  ${count}x - ${reason}`);
      });

    // Show entity extraction failures
    const failed = threads.filter(t => !t.entity_extracted && t.importance !== 'routine');
    if (failed.length > 0) {
      console.log(`\n⚠️ ENTITY EXTRACTION FAILURES (${failed.length} important emails)`);
      failed.slice(0, 5).forEach(t => {
        console.log(`  - ${t.importance}: ${t.subject.substring(0, 60)}`);
      });
    }

    // Show unlinked summaries
    if (data.unlinked_summaries && data.unlinked_summaries.length > 0) {
      console.log(`\n❌ UNLINKED SUMMARY LINES (${data.unlinked_summaries.length} lines)`);
      data.unlinked_summaries.slice(0, 5).forEach(item => {
        console.log(`  - ${item.subject.substring(0, 60)}`);
        if (item.summary_line) {
          console.log(`    Summary: ${item.summary_line.substring(0, 80)}`);
        }
      });
    }

    console.log('\n' + '='.repeat(80));
    console.log(`💾 Full report: ${apiUrl}/api/tracking/session/${sessionId}`);
    console.log('='.repeat(80) + '\n');

  } catch (error) {
    console.error('❌ Failed to fetch tracking report:', error);
  }
}

/**
 * Check if context digest is enabled
 */
async function isContextDigestEnabled() {
  try {
    const result = await chrome.storage.local.get('useContextDigest');
    // Default to true (use context digest by default)
    return result.useContextDigest !== false;
  } catch (error) {
    console.warn('⚠️ Failed to check context digest setting:', error);
    return true; // Default to enabled
  }
}

/**
 * Toggle context digest on/off
 */
async function toggleContextDigest(enabled) {
  try {
    await chrome.storage.local.set({ useContextDigest: enabled });
    console.log(`${enabled ? '✅' : '❌'} Context digest ${enabled ? 'enabled' : 'disabled'}`);
    return true;
  } catch (error) {
    console.error('❌ Failed to toggle context digest:', error);
    return false;
  }
}

/**
 * Set custom user name for personalized greetings
 * @param {string} name - User's first name (or empty to use auto-detected)
 */
async function setUserName(name) {
  try {
    if (name && name.trim()) {
      await chrome.storage.local.set({ userName: name.trim() });
      _cachedUserName = name.trim();
      console.log(`✅ User name set to: ${name.trim()}`);
    } else {
      await chrome.storage.local.remove('userName');
      _cachedUserName = null;  // Will re-detect on next call
      console.log('✅ User name cleared (will auto-detect)');
    }
    return true;
  } catch (error) {
    console.error('❌ Failed to set user name:', error);
    return false;
  }
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    generateContextDigestHTML,
    isContextDigestEnabled,
    toggleContextDigest,
    getUserFirstName,
    setUserName
  };
}
