"""
DEPRECATED: This module has moved to shared/redirect_circuit_breaker.py
=======================================================================
Date: 2026-03-15
Reason: Circuit breaker now used by both Parser and Enricher

This file exists for backward compatibility only.
All new code should import from shared.redirect_circuit_breaker instead.

Usage:
    # OLD (deprecated)
    from persistence.redirect_circuit_breaker import should_attempt_redirect

    # NEW (correct)
    from shared.redirect_circuit_breaker import should_attempt_redirect
"""

import sys
import os

# Add shared directory to path
sys.path.insert(0, '/opt/python')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Re-export all functions from shared module
try:
    from shared.redirect_circuit_breaker import (
        should_attempt_redirect,
        should_route_to_playwright,
        update_redirect_tracking,
        get_redirect_tracking_status
    )
except ImportError:
    # Fallback for local testing
    from redirect_circuit_breaker import (
        should_attempt_redirect,
        should_route_to_playwright,
        update_redirect_tracking,
        get_redirect_tracking_status
    )

__all__ = [
    'should_attempt_redirect',
    'should_route_to_playwright',
    'update_redirect_tracking',
    'get_redirect_tracking_status',
]
