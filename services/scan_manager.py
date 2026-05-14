"""
Scan Manager - Thread-Safe Progress Tracking

Replaces global scan_progress dictionary with proper class.
Single Responsibility: Track scan progress safely.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScanProgress:
    """Data class for scan progress tracking"""
    active: bool = False
    current: int = 0
    total: int = 0
    status: str = ''
    new_count: int = 0
    existing_count: int = 0
    start_time: float = 0
    abort: bool = False

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'active': self.active,
            'current': self.current,
            'total': self.total,
            'status': self.status,
            'new_count': self.new_count,
            'existing_count': self.existing_count,
            'start_time': self.start_time,
            'abort': self.abort
        }


class ScanManager:
    """
    Thread-safe scan progress manager.

    Handles progress tracking for Gmail inbox scans.
    Can support multiple concurrent scans in the future.
    """

    def __init__(self):
        """Initialize scan manager with thread lock"""
        self._progress = ScanProgress()
        self._lock = threading.Lock()

    def start_scan(self, time_range):
        """
        Start a new scan.

        Args:
            time_range (str): Time range for scan

        Returns:
            bool: True if scan started, False if already in progress
        """
        with self._lock:
            if self._progress.active:
                return False

            self._progress = ScanProgress(
                active=True,
                status='Starting scan...',
                start_time=time.time()
            )
            return True

    def update_status(self, status):
        """
        Update scan status message.

        Args:
            status (str): Status message
        """
        with self._lock:
            self._progress.status = status

    def update_progress(self, current, total=None):
        """
        Update scan progress.

        Args:
            current (int): Current item number
            total (int, optional): Total items (if known)
        """
        with self._lock:
            self._progress.current = current
            if total is not None:
                self._progress.total = total

    def increment_new(self):
        """Increment count of new review emails"""
        with self._lock:
            self._progress.new_count += 1

    def increment_existing(self):
        """Increment count of existing review emails"""
        with self._lock:
            self._progress.existing_count += 1

    def set_total(self, total):
        """
        Set total number of items to process.

        Args:
            total (int): Total items
        """
        with self._lock:
            self._progress.total = total

    def check_abort(self):
        """
        Check if scan should be aborted.

        Returns:
            bool: True if abort requested
        """
        with self._lock:
            return self._progress.abort

    def request_abort(self):
        """Request scan to abort"""
        with self._lock:
            if self._progress.active:
                self._progress.abort = True
                return True
            return False

    def finish_scan(self, success=True):
        """
        Mark scan as finished.

        Args:
            success (bool): Whether scan completed successfully
        """
        with self._lock:
            if self._progress.abort:
                self._progress.status = 'Scan aborted'
            elif success:
                self._progress.status = 'Scan complete'
            else:
                self._progress.status = 'Scan failed'

            self._progress.active = False

    def get_progress(self):
        """
        Get current progress snapshot.

        Returns:
            dict: Progress data with calculated estimates
        """
        with self._lock:
            progress = self._progress.to_dict()

        # Calculate time estimate (outside lock for performance)
        if progress['active'] and progress['current'] > 0:
            elapsed = time.time() - progress['start_time']
            per_item = elapsed / progress['current']
            remaining = progress['total'] - progress['current']
            progress['estimated_seconds'] = int(remaining * per_item)
        else:
            progress['estimated_seconds'] = 0

        return progress

    def is_active(self):
        """
        Check if scan is currently active.

        Returns:
            bool: True if scan is active
        """
        with self._lock:
            return self._progress.active

    def reset(self):
        """Reset progress to initial state"""
        with self._lock:
            self._progress = ScanProgress()


# Global singleton instance
_scan_manager = ScanManager()


def get_scan_manager():
    """
    Get the global scan manager instance.

    Returns:
        ScanManager: Global scan manager
    """
    return _scan_manager
