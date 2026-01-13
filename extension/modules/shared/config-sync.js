/**
 * Configuration Synchronization Module
 *
 * Fetches and syncs confidence thresholds from backend to ensure
 * frontend and backend use consistent values.
 */

// Cached configuration
let cachedThresholds = null;
let cachedTestMode = null;
let lastFetchTime = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Fetch confidence thresholds from backend
 *
 * @returns {Promise<Object>} Thresholds object
 */
async function fetchConfidenceThresholds() {
  try {
    const url = `${CONFIG.SHOPQ_API_URL}/api/config/confidence`;
    console.log('🔄 Fetching confidence thresholds from backend:', url);

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    // Extract thresholds from response
    const thresholds = data.thresholds;

    console.log('✅ Confidence thresholds loaded:', {
      type_min: thresholds.classification.type_min,
      label_min: thresholds.classification.label_min,
      type_gate: thresholds.mapper.type_gate,
      domain_gate: thresholds.mapper.domain_gate,
      attention_gate: thresholds.mapper.attention_gate
    });

    // Cache the thresholds
    cachedThresholds = thresholds;
    lastFetchTime = Date.now();

    return thresholds;
  } catch (error) {
    console.error('❌ Failed to fetch confidence thresholds:', error);

    // Return fallback defaults (match backend hardcoded values)
    console.warn('⚠️ Using fallback confidence thresholds');
    return {
      classification: {
        type_min: 0.70,
        label_min: 0.70
      },
      mapper: {
        type_gate: 0.70,
        domain_gate: 0.70,
        attention_gate: 0.70
      }
    };
  }
}

/**
 * Get confidence thresholds (uses cache if available)
 *
 * @param {boolean} forceRefresh - Force refresh from backend
 * @returns {Promise<Object>} Thresholds object
 */
async function getConfidenceThresholds(forceRefresh = false) {
  // Check cache validity
  const cacheValid = cachedThresholds &&
                     lastFetchTime &&
                     (Date.now() - lastFetchTime) < CACHE_TTL;

  if (!forceRefresh && cacheValid) {
    return cachedThresholds;
  }

  // Fetch fresh thresholds
  return await fetchConfidenceThresholds();
}

/**
 * Validate classification result meets confidence thresholds
 *
 * @param {Object} classification - Classification result from backend
 * @param {Object} thresholds - Confidence thresholds (optional, will fetch if not provided)
 * @returns {Promise<Object>} Validation result: { valid: boolean, warnings: string[] }
 */
async function validateClassification(classification, thresholds = null) {
  if (!thresholds) {
    thresholds = await getConfidenceThresholds();
  }

  const warnings = [];

  // Skip validation for rule/detector/fallback results (they're pre-validated and always trusted)
  // - 'rule': From rules engine (Phase 1)
  // - 'detector': From detectors (Phase 2)
  // - 'fallback': Backend already filtered this as low confidence -> Uncategorized
  if (classification.decider === 'rule' ||
      classification.decider === 'detector' ||
      classification.decider === 'fallback') {
    return {
      valid: true,
      warnings: [],
      skipped: true  // Indicate this was intentionally skipped
    };
  }

  // Only validate LLM results (decider === 'gemini')
  // Check type confidence
  if (classification.type_conf < thresholds.classification.type_min) {
    warnings.push(
      `Type confidence ${classification.type_conf.toFixed(2)} below threshold ${thresholds.classification.type_min}`
    );
  }

  // NOTE: Domain validation removed - domains are deprecated in current taxonomy
  // Classification now uses type + importance + attention only

  // Check attention confidence
  if (classification.attention !== 'none' &&
      classification.attention_conf < thresholds.mapper.attention_gate) {
    warnings.push(
      `Attention confidence ${classification.attention_conf.toFixed(2)} below threshold ${thresholds.mapper.attention_gate}`
    );
  }

  return {
    valid: warnings.length === 0,
    warnings: warnings
  };
}

/**
 * Validate batch of classifications
 *
 * @param {Array} classifications - Array of classification results
 * @returns {Promise<Object>} Validation summary
 */
async function validateClassificationBatch(classifications) {
  // Defensive check: ensure classifications is an array
  if (!classifications || !Array.isArray(classifications) || classifications.length === 0) {
    console.warn('⚠️ Confidence validation skipped: No classifications to validate');
    return {
      total: 0,
      valid: 0,
      invalid: 0,
      warnings: []
    };
  }

  const thresholds = await getConfidenceThresholds();

  let validCount = 0;
  let invalidCount = 0;
  let skippedCount = 0;  // Track rule/detector results (no validation needed)
  const allWarnings = [];

  for (const classification of classifications) {
    // Skip if classification is invalid
    if (!classification) {
      continue;
    }

    const validation = await validateClassification(classification, thresholds);

    if (validation.skipped) {
      // Rule/detector result - no validation needed (always trusted)
      skippedCount++;
      validCount++;  // Count as valid since it's pre-validated
    } else if (validation.valid) {
      validCount++;
    } else {
      invalidCount++;

      // Log individual warnings for LLM results only
      if (validation.warnings && validation.warnings.length > 0) {
        console.warn(`⚠️ Low confidence for ${classification.type} from ${classification.from || 'unknown'}:`);
        validation.warnings.forEach(w => console.warn(`   - ${w}`));

        allWarnings.push({
          classification: classification,
          warnings: validation.warnings
        });
      }
    }
  }

  // Summary - only warn if majority of LLM results are below threshold
  const llmCount = classifications.length - skippedCount;  // Only LLM results were validated

  if (llmCount === 0) {
    // All classifications from rules/detectors - perfect!
    console.log(`✅ Confidence validation: ${validCount}/${classifications.length} valid (${skippedCount} from rules/detectors, 0 from LLM)`);
  } else {
    const percentBelow = (invalidCount / llmCount) * 100;

    if (percentBelow > 75) {
      // Majority of LLM results are low confidence - real issue
      console.warn(`⚠️ Confidence validation: ${invalidCount}/${llmCount} LLM classifications (${percentBelow.toFixed(0)}%) below threshold - backend may be misconfigured`);
    } else if (invalidCount > 0) {
      // Some low confidence LLM results - normal
      console.log(`ℹ️  Confidence info: ${validCount}/${classifications.length} valid (${skippedCount} rules/detectors, ${llmCount - invalidCount}/${llmCount} LLM above threshold)`);
    } else {
      // All LLM results meet threshold
      console.log(`✅ Confidence validation: ${validCount}/${classifications.length} valid (${skippedCount} rules/detectors, ${llmCount} LLM)`);
    }
  }

  return {
    total: classifications.length,
    valid: validCount,
    invalid: invalidCount,
    skipped: skippedCount,
    warnings: allWarnings
  };
}

/**
 * Fetch test mode status from backend
 *
 * @returns {Promise<boolean>} Test mode enabled status
 */
async function fetchTestMode() {
  try {
    const url = `${CONFIG.SHOPQ_API_URL}/api/test/mode`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    const testModeEnabled = data.test_mode_enabled;

    console.log(testModeEnabled
      ? '🧪 Test mode ENABLED - cache disabled, rules skipped, no learning'
      : '✅ Test mode disabled - normal operation');

    // Update CONFIG dynamically
    CONFIG.TUNING_MODE = testModeEnabled;
    cachedTestMode = testModeEnabled;

    return testModeEnabled;
  } catch (error) {
    console.error('❌ Failed to fetch test mode status:', error);
    console.warn('⚠️ Using local TUNING_MODE config value');
    return CONFIG.TUNING_MODE;
  }
}

/**
 * Initialize config sync on extension startup
 */
async function initConfigSync() {
  console.log('🚀 Initializing config sync...');

  try {
    // Fetch both thresholds and test mode in parallel
    await Promise.all([
      fetchConfidenceThresholds(),
      fetchTestMode()
    ]);
    console.log('✅ Config sync initialized');
  } catch (error) {
    console.error('❌ Config sync initialization failed:', error);
  }
}

// Auto-initialize on load
if (typeof chrome !== 'undefined' && chrome.runtime) {
  // Wait a bit to ensure CONFIG is loaded
  setTimeout(initConfigSync, 1000);
}
