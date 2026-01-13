"""
Tests for feature flag system.

Tests:
- Percentage-based rollout
- User-based consistent hashing
- Environment variable overrides
- Flag not found behavior
- Singleton instance behavior
"""

import os
from unittest import mock

from mailq.runtime.flags import FeatureFlags, get_feature_flags, is_enabled


class TestFeatureFlagsBasic:
    """Tests for basic FeatureFlags functionality"""

    def test_flag_enabled_by_default(self):
        """Test that DIGEST_V2 is enabled by default (100% rollout - V1 deprecated)"""
        with mock.patch.dict(os.environ, {}, clear=True):
            flags = FeatureFlags()
            assert flags.is_enabled("DIGEST_V2", user_id="test_user")

    def test_flag_100_percent_rollout(self):
        """Test that 100% rollout enables for all users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "100"}):
            flags = FeatureFlags()
            assert flags.is_enabled("DIGEST_V2", user_id="user1")
            assert flags.is_enabled("DIGEST_V2", user_id="user2")
            assert flags.is_enabled("DIGEST_V2", user_id="user3")

    def test_flag_not_found_returns_default(self):
        """Test that unknown flags return default value"""
        flags = FeatureFlags()
        assert not flags.is_enabled("UNKNOWN_FLAG", default=False)
        assert flags.is_enabled("UNKNOWN_FLAG", default=True)

    def test_explicit_override_true(self):
        """Test that FORCE_DIGEST_V2=true overrides rollout percentage"""
        with mock.patch.dict(
            os.environ, {"FORCE_DIGEST_V2": "true", "DIGEST_V2_ROLLOUT_PERCENTAGE": "0"}
        ):
            flags = FeatureFlags()
            # Should be enabled despite 0% rollout
            assert flags.is_enabled("DIGEST_V2", user_id="test_user")

    def test_explicit_override_false(self):
        """Test that FORCE_DIGEST_V2=false overrides rollout percentage"""
        with mock.patch.dict(
            os.environ, {"FORCE_DIGEST_V2": "false", "DIGEST_V2_ROLLOUT_PERCENTAGE": "100"}
        ):
            flags = FeatureFlags()
            # Should be disabled despite 100% rollout
            assert not flags.is_enabled("DIGEST_V2", user_id="test_user")

    def test_no_user_id_returns_false_for_safety(self):
        """Test that partial rollout without user_id defaults to disabled"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags = FeatureFlags()
            # Should be disabled for safety (avoid non-deterministic behavior)
            assert not flags.is_enabled("DIGEST_V2", user_id=None)


class TestConsistentHashing:
    """Tests for user-based consistent hashing"""

    def test_same_user_gets_consistent_result(self):
        """Test that same user_id always gets same result"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags = FeatureFlags()
            user_id = "test_user_123"

            # Call multiple times - should be consistent
            result1 = flags.is_enabled("DIGEST_V2", user_id=user_id)
            result2 = flags.is_enabled("DIGEST_V2", user_id=user_id)
            result3 = flags.is_enabled("DIGEST_V2", user_id=user_id)

            assert result1 == result2 == result3

    def test_different_users_get_distributed_results(self):
        """Test that 50% rollout enables for ~50% of users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags = FeatureFlags()

            # Test 100 different users
            enabled_count = 0
            for i in range(100):
                user_id = f"user_{i}"
                if flags.is_enabled("DIGEST_V2", user_id=user_id):
                    enabled_count += 1

            # Should be roughly 50% (allow 30-70% range for hash distribution variance)
            assert 30 <= enabled_count <= 70, f"Expected ~50%, got {enabled_count}%"

    def test_low_percentage_rollout(self):
        """Test that 10% rollout enables for ~10% of users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "10"}):
            flags = FeatureFlags()

            enabled_count = 0
            for i in range(100):
                user_id = f"user_{i}"
                if flags.is_enabled("DIGEST_V2", user_id=user_id):
                    enabled_count += 1

            # Should be roughly 10% (allow 3-20% range for variance)
            assert 3 <= enabled_count <= 20, f"Expected ~10%, got {enabled_count}%"

    def test_hash_function_is_deterministic(self):
        """Test that hash-based rollout is deterministic across instances"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags1 = FeatureFlags()
            flags2 = FeatureFlags()

            user_id = "deterministic_test_user"

            # Should get same result from different instances
            assert flags1.is_enabled("DIGEST_V2", user_id=user_id) == flags2.is_enabled(
                "DIGEST_V2", user_id=user_id
            )


class TestEnvironmentVariableParsing:
    """Tests for environment variable parsing"""

    def test_boolean_parsing_variations(self):
        """Test various boolean string formats"""
        # Test "true" variations
        for value in ["true", "True", "TRUE", "1", "yes", "YES"]:
            with mock.patch.dict(os.environ, {"FORCE_DIGEST_V2": value}):
                flags = FeatureFlags()
                assert flags.is_enabled("DIGEST_V2", user_id="test")

        # Test "false" variations
        for value in ["false", "False", "FALSE", "0", "no", "NO"]:
            with mock.patch.dict(os.environ, {"FORCE_DIGEST_V2": value}):
                flags = FeatureFlags()
                assert not flags.is_enabled("DIGEST_V2", user_id="test")

    def test_invalid_boolean_uses_default(self):
        """Test that invalid boolean values use default"""
        with mock.patch.dict(os.environ, {"FORCE_DIGEST_V2": "invalid"}):
            flags = FeatureFlags()
            # Should fall back to percentage-based (100% by default since V1 deprecated)
            assert flags.is_enabled("DIGEST_V2", user_id="test")

    def test_integer_parsing(self):
        """Test that percentage is parsed as integer"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "75"}):
            flags = FeatureFlags()
            assert flags.flags["DIGEST_V2"]["rollout_percentage"] == 75

    def test_invalid_integer_uses_default(self):
        """Test that invalid integer values use default (100 since V1 deprecated)"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "not_a_number"}):
            flags = FeatureFlags()
            assert flags.flags["DIGEST_V2"]["rollout_percentage"] == 100


class TestSingletonBehavior:
    """Tests for global singleton instance"""

    def test_get_feature_flags_returns_singleton(self):
        """Test that get_feature_flags returns same instance"""
        # Clear singleton for test
        import mailq.runtime.flags as flags_module

        flags_module._feature_flags = None

        flags1 = get_feature_flags()
        flags2 = get_feature_flags()

        assert flags1 is flags2

    def test_is_enabled_convenience_function(self):
        """Test that is_enabled() convenience function works"""
        with mock.patch.dict(os.environ, {"FORCE_DIGEST_V2": "true"}):
            # Clear singleton for test
            import mailq.runtime.flags as flags_module

            flags_module._feature_flags = None

            # Should use singleton
            assert is_enabled("DIGEST_V2", user_id="test")

    def test_get_all_flags(self):
        """Test that get_all_flags returns copy of flags dict"""
        flags = FeatureFlags()
        all_flags = flags.get_all_flags()

        # Should be a copy, not the original
        assert all_flags is not flags.flags
        assert all_flags == flags.flags

        # Modifying returned dict should not affect original
        all_flags["NEW_FLAG"] = {"enabled": True}
        assert "NEW_FLAG" not in flags.flags


class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_empty_user_id_treated_as_none(self):
        """Test that empty string user_id is treated as None"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags = FeatureFlags()
            # Empty string should be treated as no user_id
            assert not flags.is_enabled("DIGEST_V2", user_id="")

    def test_percentage_boundary_0(self):
        """Test that 0% rollout disables for all users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "0"}):
            flags = FeatureFlags()
            for i in range(10):
                assert not flags.is_enabled("DIGEST_V2", user_id=f"user_{i}")

    def test_percentage_boundary_100(self):
        """Test that 100% rollout enables for all users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "100"}):
            flags = FeatureFlags()
            for i in range(10):
                assert flags.is_enabled("DIGEST_V2", user_id=f"user_{i}")

    def test_percentage_over_100_treated_as_100(self):
        """Test that percentages > 100 enable for all users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "150"}):
            flags = FeatureFlags()
            for i in range(10):
                assert flags.is_enabled("DIGEST_V2", user_id=f"user_{i}")

    def test_negative_percentage_disables_all(self):
        """Test that negative percentages disable for all users"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "-10"}):
            flags = FeatureFlags()
            for i in range(10):
                assert not flags.is_enabled("DIGEST_V2", user_id=f"user_{i}")

    def test_unicode_user_id(self):
        """Test that unicode user_ids are handled correctly"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags = FeatureFlags()
            user_id = "user_🚀_测试"
            # Should not crash and should be consistent
            result1 = flags.is_enabled("DIGEST_V2", user_id=user_id)
            result2 = flags.is_enabled("DIGEST_V2", user_id=user_id)
            assert result1 == result2

    def test_very_long_user_id(self):
        """Test that very long user_ids are handled correctly"""
        with mock.patch.dict(os.environ, {"DIGEST_V2_ROLLOUT_PERCENTAGE": "50"}):
            flags = FeatureFlags()
            user_id = "user_" + ("a" * 10000)  # 10KB user_id
            # Should not crash and should be consistent
            result1 = flags.is_enabled("DIGEST_V2", user_id=user_id)
            result2 = flags.is_enabled("DIGEST_V2", user_id=user_id)
            assert result1 == result2
