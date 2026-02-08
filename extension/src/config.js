/**
 * Shared configuration for webpack-bundled content script.
 *
 * These values MUST match extension/modules/shared/config.js (the service
 * worker config). Keeping them in sync is the responsibility of Phase 0.
 */

export const API_BASE_URL = 'https://reclaim-api-488078904670.us-central1.run.app';

export const DIGEST_REFRESH_DEBOUNCE_MS = 5000;
export const SIDEBAR_REFRESH_INTERVAL_MS = 60000;
export const LABEL_CACHE_KEY = 'shopq_label_cache';
