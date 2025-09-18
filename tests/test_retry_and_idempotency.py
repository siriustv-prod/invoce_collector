#!/usr/bin/env python3
"""
Pytest test suite proving retry mechanism and tiny idempotency key behavior
for the Zoho Books Invoice Collector.
"""

import pytest
import os
import sys
import json
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add parent directory to path to import our module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zoho_paid_invoce_collector_script import (
    exponential_backoff_retry,
    get_csv_filename,
    _idem_load,
    _idem_save,
    maybe_replay,
    record_result,
    safe_goto,
    safe_wait_for_selector,
    safe_click,
    IDEM_FILE,
    IDEM_TTL_SECONDS
)


class TestRetryMechanism:
    """Test the exponential backoff retry decorator."""
    
    def test_successful_operation_no_retry(self):
        """Test that successful operations don't trigger retries."""
        call_count = 0
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.01)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_func()
        
        assert result == "success"
        assert call_count == 1, "Should only be called once for successful operation"
    
    def test_retry_on_429_error(self):
        """Test retry behavior on 429 rate limiting error."""
        call_count = 0
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.01)
        def rate_limited_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 Rate limited")
            return "success after retries"
        
        result = rate_limited_func()
        
        assert result == "success after retries"
        assert call_count == 3, "Should retry twice before succeeding"
    
    def test_retry_on_5xx_error(self):
        """Test retry behavior on 5xx server errors."""
        call_count = 0
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.01)
        def server_error_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("500 Internal Server Error")
            return "recovered"
        
        result = server_error_func()
        
        assert result == "recovered"
        assert call_count == 2, "Should retry once before succeeding"
    
    def test_no_retry_on_non_retryable_error(self):
        """Test that non-retryable errors don't trigger retries."""
        call_count = 0
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.01)
        def non_retryable_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("400 Bad Request - not retryable")
        
        with pytest.raises(ValueError):
            non_retryable_func()
        
        assert call_count == 1, "Should not retry non-retryable errors"
    
    def test_max_attempts_exceeded(self):
        """Test that function fails after max attempts."""
        call_count = 0
        
        @exponential_backoff_retry(max_attempts=2, base_delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise Exception("429 Always fails")
        
        with pytest.raises(Exception) as exc_info:
            always_fails()
        
        assert "429" in str(exc_info.value)
        assert call_count == 2, "Should attempt exactly max_attempts times"
    
    def test_exponential_backoff_timing(self):
        """Test that retry delays follow exponential backoff pattern."""
        call_times = []
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.1, max_delay=1.0)
        def timing_test():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise Exception("timeout error")
            return "success"
        
        start_time = time.time()
        result = timing_test()
        
        assert result == "success"
        assert len(call_times) == 3
        
        # Check that delays are increasing (allowing for some timing variance)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        
        # First delay should be around 0.1s, second around 0.2s (with jitter)
        assert 0.05 < delay1 < 0.3, f"First delay {delay1} not in expected range"
        assert 0.1 < delay2 < 0.6, f"Second delay {delay2} not in expected range"
        assert delay2 > delay1 * 0.8, "Second delay should be larger than first"


class TestTinyIdempotency:
    """Test the tiny idempotency key functionality."""
    
    def test_csv_filename_generation(self):
        """Test CSV filename generation based on idempotency key."""
        # No key - default filename
        assert get_csv_filename(None) == "collected_data/invoices.csv"
        assert get_csv_filename("") == "collected_data/invoices.csv"
        
        # With key - key-specific filename
        assert get_csv_filename("daily-run-2025-09-18") == "collected_data/invoices_daily-run-2025-09-18.csv"
        assert get_csv_filename("weekly-report") == "collected_data/invoices_weekly-report.csv"
        
        # Special characters should be sanitized
        assert get_csv_filename("test/key:with*special?chars") == "collected_data/invoices_test_key_with_special_chars.csv"
        assert get_csv_filename("key with spaces") == "collected_data/invoices_key_with_spaces.csv"
    
    def setup_method(self):
        """Set up test environment with temporary files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_idem_file = os.path.join(self.temp_dir, ".idem_cache.json")
        
        # Patch the IDEM_FILE constant for testing
        self.idem_patcher = patch('zoho_paid_invoce_collector_script.IDEM_FILE', 
                                 self.temp_idem_file)
        self.idem_patcher.start()
    
    def teardown_method(self):
        """Clean up test environment."""
        self.idem_patcher.stop()
        # Clean up temp files
        if os.path.exists(self.temp_idem_file):
            os.remove(self.temp_idem_file)
        os.rmdir(self.temp_dir)
    
    def test_replay_round_trip(self):
        """Test complete idempotency round trip: record → replay → expire."""
        key = "test-key-123"
        
        # Initially no replay available
        assert maybe_replay(key) is None
        
        # Record a result
        summary = {"rows": 5, "csv": "collected_data/invoices_test-key-123.csv"}
        record_result(key, summary)
        
        # Should replay the same result
        replayed = maybe_replay(key)
        assert replayed == summary
        
        # Expire the entry by manipulating timestamp
        data = _idem_load()
        data[key]["ts"] = time.time() - (IDEM_TTL_SECONDS + 1)
        _idem_save(data)
        
        # Should no longer replay
        assert maybe_replay(key) is None
    
    def test_no_key_behavior(self):
        """Test behavior when no idempotency key is provided."""
        # Should return None for all operations
        assert maybe_replay(None) is None
        assert maybe_replay("") is None
        
        # Recording with no key should be no-op
        record_result(None, {"test": "data"})
        record_result("", {"test": "data"})
        
        # File should not be created
        assert not os.path.exists(self.temp_idem_file)
    
    def test_multiple_keys(self):
        """Test that different keys are handled independently."""
        key1 = "daily-run-2025-09-18"
        key2 = "weekly-report-2025-09-18"
        
        summary1 = {"rows": 10, "csv": "collected_data/invoices_daily-run-2025-09-18.csv"}
        summary2 = {"rows": 50, "csv": "collected_data/invoices_weekly-report-2025-09-18.csv"}
        
        # Record different results for different keys
        record_result(key1, summary1)
        record_result(key2, summary2)
        
        # Each key should replay its own result
        assert maybe_replay(key1) == summary1
        assert maybe_replay(key2) == summary2
        
        # Non-existent key should return None
        assert maybe_replay("non-existent") is None
    
    def test_cache_file_operations(self):
        """Test low-level cache file operations."""
        # Test empty cache
        data = _idem_load()
        assert data == {}
        
        # Test saving and loading
        test_data = {
            "key1": {"ts": time.time(), "summary": {"rows": 1}},
            "key2": {"ts": time.time(), "summary": {"rows": 2}}
        }
        _idem_save(test_data)
        
        # Verify file exists
        assert os.path.exists(self.temp_idem_file)
        
        # Load and verify
        loaded = _idem_load()
        assert "key1" in loaded
        assert "key2" in loaded
        assert loaded["key1"]["summary"]["rows"] == 1
        assert loaded["key2"]["summary"]["rows"] == 2
    
    def test_corrupted_cache_file(self):
        """Test handling of corrupted cache file."""
        # Create corrupted JSON file
        with open(self.temp_idem_file, 'w') as f:
            f.write("invalid json content")
        
        # Should return empty dict instead of crashing
        data = _idem_load()
        assert data == {}
        
        # Should be able to save new data
        record_result("test-key", {"rows": 1})
        
        # Should be able to replay
        replayed = maybe_replay("test-key")
        assert replayed == {"rows": 1}


class TestSafeOperations:
    """Test the safe Playwright operations with retry mechanisms."""
    
    def test_safe_goto_success(self):
        """Test successful navigation with safe_goto."""
        # Mock page and response
        mock_page = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        
        result = safe_goto(mock_page, "https://example.com")
        
        assert result == mock_response
        mock_page.goto.assert_called_once_with("https://example.com")
        mock_page.wait_for_load_state.assert_called_once_with("networkidle")
    
    def test_safe_goto_retry_on_server_error(self):
        """Test that safe_goto retries on server errors."""
        mock_page = Mock()
        
        # First call returns 500, second call succeeds
        mock_response_error = Mock()
        mock_response_error.status = 500
        mock_response_success = Mock()
        mock_response_success.status = 200
        
        mock_page.goto.side_effect = [mock_response_error, mock_response_success]
        
        result = safe_goto(mock_page, "https://example.com")
        
        assert result == mock_response_success
        assert mock_page.goto.call_count == 2
    
    def test_safe_wait_for_selector_success(self):
        """Test successful selector waiting."""
        mock_page = Mock()
        mock_element = Mock()
        mock_page.wait_for_selector.return_value = mock_element
        
        # Remove status attribute to avoid comparison issues in retry decorator
        del mock_element.status
        
        result = safe_wait_for_selector(mock_page, "table", timeout=5000)
        
        assert result == mock_element
        mock_page.wait_for_selector.assert_called_once_with("table", timeout=5000)
    
    def test_safe_click_success(self):
        """Test successful clicking with safe_click."""
        mock_page = Mock()
        mock_locator = Mock()
        
        result = safe_click(mock_page, mock_locator)
        
        assert result == True
        mock_locator.click.assert_called_once()
        mock_page.wait_for_load_state.assert_called_once_with("networkidle")


class TestIntegrationBehavior:
    """Integration test proving the complete retry + tiny idempotency behavior."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_idem_file = os.path.join(self.temp_dir, ".idem_cache.json")
        
        # Patch the IDEM_FILE constant
        self.idem_patcher = patch('zoho_paid_invoce_collector_script.IDEM_FILE', 
                                 self.temp_idem_file)
        self.idem_patcher.start()
    
    def teardown_method(self):
        """Clean up test environment."""
        self.idem_patcher.stop()
        if os.path.exists(self.temp_idem_file):
            os.remove(self.temp_idem_file)
        os.rmdir(self.temp_dir)
    
    def test_complete_job_lifecycle_with_idempotency(self):
        """
        Integration test proving the complete behavior:
        1. Job runs fresh when no idempotency key cached
        2. Retry mechanism works during job execution
        3. Result is cached after successful completion
        4. Subsequent runs with same key replay cached result
        5. Expired cache entries are ignored
        """
        # Simulate a scraping job that fails twice then succeeds
        operation_calls = []
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.01)
        def simulated_scraping_job():
            operation_calls.append(time.time())
            
            # Fail first two attempts with retryable errors
            if len(operation_calls) <= 2:
                raise Exception("429 Rate limited - simulated failure")
            
            # Succeed on third attempt
            return [
                {"invoice_id": "INV001", "customer": "Test Corp", "amount": "$1000"},
                {"invoice_id": "INV002", "customer": "Demo LLC", "amount": "$2000"}
            ]
        
        idem_key = "integration-test-2025-09-18"
        
        # 1. First run - no cached result
        assert maybe_replay(idem_key) is None
        
        # 2. Execute job with retries
        invoices = simulated_scraping_job()
        
        # Verify retry behavior
        assert len(operation_calls) == 3  # Failed twice, succeeded third time
        assert len(invoices) == 2
        assert invoices[0]["invoice_id"] == "INV001"
        
        # 3. Record successful result
        summary = {"rows": len(invoices), "csv": "collected_data/invoices_integration-test-2025-09-18.csv"}
        record_result(idem_key, summary)
        
        # 4. Second run with same key - should replay
        replayed_summary = maybe_replay(idem_key)
        assert replayed_summary == summary
        
        # Reset operation calls to verify no new scraping happens
        operation_calls.clear()
        
        # Simulate second run (should not execute scraping)
        cached_result = maybe_replay(idem_key)
        assert cached_result == summary
        assert len(operation_calls) == 0  # No new scraping calls
        
        # 5. Test cache expiration
        # Manually expire the cache entry
        data = _idem_load()
        data[idem_key]["ts"] = time.time() - (IDEM_TTL_SECONDS + 1)
        _idem_save(data)
        
        # Should no longer replay
        assert maybe_replay(idem_key) is None
        
        # 6. Verify different keys are independent
        different_key = "different-job-key"
        assert maybe_replay(different_key) is None
        
        record_result(different_key, {"rows": 99, "csv": "collected_data/invoices_different-job-key.csv"})
        assert maybe_replay(different_key) == {"rows": 99, "csv": "collected_data/invoices_different-job-key.csv"}
        
        # Original expired key should still be None
        assert maybe_replay(idem_key) is None


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
