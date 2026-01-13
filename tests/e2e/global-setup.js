/**
 * Global setup for Playwright tests
 * Ensures backend API is running before tests start
 */

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export default async function globalSetup() {
  console.log('🔧 Global Setup: Checking backend API...');

  try {
    // Check if backend is running
    const response = await fetch('http://localhost:8000/api/health').catch(() => null);

    if (!response || !response.ok) {
      console.warn('⚠️  Backend API not running on localhost:8000');
      console.warn('   Please start it with: uvicorn shopq.api:app --reload');
      console.warn('   Tests will proceed but may fail if backend is required');
    } else {
      console.log('✅ Backend API is running');
    }
  } catch (error) {
    console.warn('⚠️  Could not verify backend status:', error.message);
  }

  // Optional: Check if Gmail credentials are available
  const hasGmailAuth = process.env.GMAIL_TEST_EMAIL && process.env.GMAIL_TEST_PASSWORD;
  if (!hasGmailAuth) {
    console.warn('⚠️  Gmail test credentials not found in environment');
    console.warn('   Set GMAIL_TEST_EMAIL and GMAIL_TEST_PASSWORD for full E2E tests');
    console.warn('   Or use GMAIL_TEST_TOKEN for OAuth token-based auth');
  } else {
    console.log('✅ Gmail test credentials configured');
  }

  console.log('🚀 Starting tests...\n');
}
