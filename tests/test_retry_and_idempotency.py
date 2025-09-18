#!/usr/bin/env python3
"""
Pytest test suite proving retry mechanism and idempotency key behavior
for the Zoho Books Invoice Collector.
"""

import pytest
import os
import sys
import json
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add parent directory to path to import our module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zoho_paid_invoce_collector_script import (
    exponential_backoff_retry,
    generate_session_id,
    load_session_tracking,
    save_session_tracking,
    check_session_completed,
    safe_goto,
    safe_wait_for_selector,
    safe_click,
    IDEMPOTENCY_FILE
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


class TestIdempotencyKey:
    """Test the idempotency key and session tracking functionality."""
    
    def setup_method(self):
        """Set up test environment with temporary files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_idempotency_file = os.path.join(self.temp_dir, "test_session_tracking.json")
        
        # Patch the IDEMPOTENCY_FILE constant for testing
        self.idempotency_patcher = patch('zoho_paid_invoce_collector_script.IDEMPOTENCY_FILE', 
                                       self.temp_idempotency_file)
        self.idempotency_patcher.start()
    
    def teardown_method(self):
        """Clean up test environment."""
        self.idempotency_patcher.stop()
        # Clean up temp files
        if os.path.exists(self.temp_idempotency_file):
            os.remove(self.temp_idempotency_file)
        os.rmdir(self.temp_dir)
    
    def test_session_id_generation(self):
        """Test that session IDs are unique and properly formatted."""
        session_id1 = generate_session_id()
        session_id2 = generate_session_id()
        
        # Should be different
        assert session_id1 != session_id2
        
        # Should be valid UUID format (36 characters with hyphens)
        assert len(session_id1) == 36
        assert session_id1.count('-') == 4
        
        # Should be strings
        assert isinstance(session_id1, str)
        assert isinstance(session_id2, str)
    
    def test_session_tracking_save_and_load(self):
        """Test saving and loading session tracking data."""
        session_id = generate_session_id()
        
        test_data = {
            session_id: {
                'session_id': session_id,
                'timestamp': datetime.now().isoformat(),
                'status': 'completed',
                'invoices_collected': 42,
                'pages_processed': 3
            }
        }
        
        # Save data
        save_session_tracking(test_data)
        
        # Verify file exists
        assert os.path.exists(self.temp_idempotency_file)
        
        # Load data back
        loaded_data = load_session_tracking()
        
        assert session_id in loaded_data
        assert loaded_data[session_id]['status'] == 'completed'
        assert loaded_data[session_id]['invoices_collected'] == 42
        assert loaded_data[session_id]['pages_processed'] == 3
    
    def test_session_completion_check(self):
        """Test checking if a session was completed."""
        session_id = generate_session_id()
        
        # Initially should not be completed
        assert check_session_completed(session_id) == False
        
        # Save completed session
        test_data = {
            session_id: {
                'session_id': session_id,
                'status': 'completed',
                'timestamp': datetime.now().isoformat()
            }
        }
        save_session_tracking(test_data)
        
        # Now should be completed
        assert check_session_completed(session_id) == True
        
        # Test with failed session
        failed_session_id = generate_session_id()
        test_data[failed_session_id] = {
            'session_id': failed_session_id,
            'status': 'failed',
            'timestamp': datetime.now().isoformat()
        }
        save_session_tracking(test_data)
        
        # Failed session should not be considered completed
        assert check_session_completed(failed_session_id) == False
    
    def test_load_empty_or_missing_file(self):
        """Test loading when file doesn't exist or is empty."""
        # File doesn't exist
        loaded_data = load_session_tracking()
        assert loaded_data == {}
        
        # Create empty file
        with open(self.temp_idempotency_file, 'w') as f:
            f.write("")
        
        loaded_data = load_session_tracking()
        assert loaded_data == {}
        
        # Create invalid JSON file
        with open(self.temp_idempotency_file, 'w') as f:
            f.write("invalid json content")
        
        loaded_data = load_session_tracking()
        assert loaded_data == {}


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
    """Integration test proving the complete retry + idempotency behavior."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_idempotency_file = os.path.join(self.temp_dir, "integration_test_tracking.json")
        
        # Patch the IDEMPOTENCY_FILE constant
        self.idempotency_patcher = patch('zoho_paid_invoce_collector_script.IDEMPOTENCY_FILE', 
                                       self.temp_idempotency_file)
        self.idempotency_patcher.start()
    
    def teardown_method(self):
        """Clean up test environment."""
        self.idempotency_patcher.stop()
        if os.path.exists(self.temp_idempotency_file):
            os.remove(self.temp_idempotency_file)
        os.rmdir(self.temp_dir)
    
    def test_complete_session_lifecycle_with_retries(self):
        """
        Integration test proving the complete behavior:
        1. Session ID generation and tracking
        2. Retry mechanism on failures
        3. Session completion tracking
        4. Idempotency verification
        """
        # Simulate a function that fails twice then succeeds
        operation_calls = []
        
        @exponential_backoff_retry(max_attempts=3, base_delay=0.01)
        def simulated_scraping_operation(session_id, page_num):
            operation_calls.append((session_id, page_num))
            
            # Fail first two attempts with retryable errors
            if len(operation_calls) <= 2:
                raise Exception("429 Rate limited - simulated failure")
            
            # Succeed on third attempt
            return f"scraped_data_page_{page_num}"
        
        # 1. Generate session ID
        session_id = generate_session_id()
        assert session_id is not None
        assert len(session_id) == 36  # UUID format
        
        # 2. Initialize session tracking
        session_info = {
            'session_id': session_id,
            'timestamp': datetime.now().isoformat(),
            'status': 'started',
            'pages_processed': 0
        }
        
        tracking_data = {session_id: session_info}
        save_session_tracking(tracking_data)
        
        # Verify session was saved
        loaded_data = load_session_tracking()
        assert session_id in loaded_data
        assert loaded_data[session_id]['status'] == 'started'
        
        # 3. Simulate scraping operation with retries
        try:
            result = simulated_scraping_operation(session_id, 1)
            
            # Should succeed after retries
            assert result == "scraped_data_page_1"
            assert len(operation_calls) == 3  # Failed twice, succeeded third time
            
            # All calls should have same session_id
            for call_session_id, _ in operation_calls:
                assert call_session_id == session_id
            
            # 4. Mark session as completed
            session_info['status'] = 'completed'
            session_info['pages_processed'] = 1
            session_info['completion_timestamp'] = datetime.now().isoformat()
            tracking_data[session_id] = session_info
            save_session_tracking(tracking_data)
            
        except Exception as e:
            # Mark session as failed
            session_info['status'] = 'failed'
            session_info['error'] = str(e)
            tracking_data[session_id] = session_info
            save_session_tracking(tracking_data)
            raise
        
        # 5. Verify final session state
        final_data = load_session_tracking()
        final_session = final_data[session_id]
        
        assert final_session['status'] == 'completed'
        assert final_session['pages_processed'] == 1
        assert 'completion_timestamp' in final_session
        
        # 6. Verify idempotency check
        is_completed = check_session_completed(session_id)
        assert is_completed == True
        
        # 7. Verify that a new session would get a different ID
        new_session_id = generate_session_id()
        assert new_session_id != session_id
        assert check_session_completed(new_session_id) == False


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
