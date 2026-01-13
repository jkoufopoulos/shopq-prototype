#!/usr/bin/env python3
"""
Quick API startup test

Tests that the API can initialize successfully and the /health/db endpoint works.
"""

import sys
import time
from multiprocessing import Process


def start_api():
    """Start the API in a subprocess"""
    import uvicorn

    from shopq.api import app

    uvicorn.run(app, host="127.0.0.1", port=8888, log_level="info")


def test_api_startup():
    """Test API starts and /health/db works"""

    import requests

    # Start API in background
    print("Starting API server on http://127.0.0.1:8888...")
    api_process = Process(target=start_api)
    api_process.start()

    try:
        # Wait for server to start
        print("Waiting for server to start...")
        for i in range(30):  # Wait up to 30 seconds
            try:
                response = requests.get("http://127.0.0.1:8888/health", timeout=1)
                if response.status_code == 200:
                    print(f"✅ Server started successfully (took {i + 1}s)")
                    break
            except Exception:
                time.sleep(1)
        else:
            print("❌ Server failed to start within 30 seconds")
            return False

        # Test /health/db endpoint
        print("\nTesting /health/db endpoint...")
        response = requests.get("http://127.0.0.1:8888/health/db", timeout=5)

        if response.status_code == 200:
            data = response.json()
            print("✅ /health/db returned 200 OK")
            print(f"   Status: {data.get('status')}")
            print(f"   Pool stats: {data.get('pool')}")

            # Validate response structure
            assert "status" in data, "Response missing 'status' field"
            assert "pool" in data, "Response missing 'pool' field"

            pool = data["pool"]
            assert "pool_size" in pool, "Pool stats missing 'pool_size'"
            assert "available" in pool, "Pool stats missing 'available'"
            assert "in_use" in pool, "Pool stats missing 'in_use'"
            assert "usage_percent" in pool, "Pool stats missing 'usage_percent'"

            assert pool["pool_size"] == 5, f"Pool size should be 5, got {pool['pool_size']}"
            assert data["status"] in ["healthy", "degraded"], f"Unexpected status: {data['status']}"

            print("✅ All /health/db validations passed")
            return True
        print(f"❌ /health/db returned {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Stop API server
        print("\nStopping API server...")
        api_process.terminate()
        api_process.join(timeout=5)
        if api_process.is_alive():
            api_process.kill()
            api_process.join()
        print("✅ API server stopped")


if __name__ == "__main__":
    print("=" * 60)
    print("API Startup Test")
    print("=" * 60)
    print()

    try:
        success = test_api_startup()

        print()
        print("=" * 60)
        if success:
            print("✅ All tests PASSED")
            print("=" * 60)
            sys.exit(0)
        else:
            print("❌ Tests FAILED")
            print("=" * 60)
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
