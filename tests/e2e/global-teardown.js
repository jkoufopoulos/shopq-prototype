/**
 * Global teardown for Playwright tests
 * Cleanup after all tests complete
 */

export default async function globalTeardown() {
  console.log('\n🧹 Global Teardown: Cleaning up...');
  console.log('✅ Teardown complete');
}
