/**
 * Re-exports from the canonical config (modules/shared/config.js).
 *
 * This file exists only because webpack needs ES module imports.
 * All values flow from the single CONFIG object — no duplicates.
 */

const CONFIG = require('../modules/shared/config.js');

export const API_BASE_URL = CONFIG.API_BASE_URL;
export const DIGEST_REFRESH_DEBOUNCE_MS = CONFIG.DIGEST_REFRESH_DEBOUNCE_MS;
export const SIDEBAR_REFRESH_INTERVAL_MS = CONFIG.SIDEBAR_REFRESH_INTERVAL_MS;
export const LABEL_CACHE_KEY = CONFIG.KEYS.LABEL_CACHE;
