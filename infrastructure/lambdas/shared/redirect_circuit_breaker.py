"""
URL Redirect Circuit Breaker - Prevent retry loops on Cloudflare-protected sites
==================================================================================
Purpose: Track redirect failures per company, route to Playwright after N failures
Pattern: Circuit Breaker with graceful fallback

Timezone: Eastern Time (ET) - Business day alignment
- "New day" = 12:00 AM ET (not UTC)
- Aligns with company press release schedules (9 AM - 5 PM ET)

State Machine:
--------------
Day 1, PR #1: Try redirect → FAIL → Route to Playwright, record failure #1
Day 1, PR #2: Already failed today → Route to Playwright (no retry)
Day 2, PR #1: Try redirect → FAIL → Route to Playwright, record failure #2
Day 3, PR #1: Try redirect → FAIL → Route to Playwright, record failure #3
Day 4+: failure_count >= 3 → Permanently route to Playwright (no redirect attempts)

On ANY success: Reset failure_count to 0, revert to redirect-first approach

DynamoDB Fields (reitsheet-companies-config):
----------------------------------------------
{
  "redirect_failure_count": 0,              // Integer, consecutive failure days
  "last_redirect_attempt_date": null,       // String (YYYY-MM-DD), last redirect attempt
  "last_redirect_failure_date": null,       // String (YYYY-MM-DD), last failure
  "redirect_failure_threshold": 3,          // Integer, default 3 days
  "redirect_strategy": "redirect_first"     // String: "redirect_first" or "playwright_permanent"
}

SOLID Principles:
-----------------
- Single Responsibility: Only manages redirect failure tracking
- Open/Closed: Threshold configurable per company
- Dependency Injection: DynamoDB table passed as parameter
- Interface Segregation: Small, focused functions

Last Updated: 2026-03-15 (ET timezone conversion)
"""

import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger()

# NOTE: today_iso parameter should be in ET timezone (use shared.timezone_utils.get_today_et())
# Do NOT pass datetime.now(timezone.utc) - it will cause timezone mismatch!


def should_attempt_redirect(company_config: Dict[str, Any], today_iso: str) -> Tuple[bool, bool, str]:
    """
    Check if redirect should be attempted based on circuit breaker state.

    Rules:
    1. If failure_count >= threshold → Return (False, True, "permanent_playwright")
    2. If last_attempt_date == today → Return (False, True, "failed_today_use_playwright")
    3. Otherwise → Return (True, False, "allowed")

    Args:
        company_config: Company configuration from DynamoDB
        today_iso: Today's date in YYYY-MM-DD format

    Returns:
        Tuple of:
        - should_attempt: bool - Should try redirect
        - should_use_playwright: bool - Should route to Playwright instead
        - reason: str - Why (for logging)
    """
    # Get circuit breaker fields (with defaults for backward compatibility)
    # Convert to int in case DynamoDB stored as string
    failure_count = int(company_config.get('redirect_failure_count', 0) or 0)
    last_attempt_date = company_config.get('last_redirect_attempt_date')
    redirect_strategy = company_config.get('redirect_strategy', 'redirect_first')
    threshold = int(company_config.get('redirect_failure_threshold', 3) or 3)

    # Rule 1: Circuit breaker active (permanent Playwright routing)
    if redirect_strategy == 'playwright_permanent' or failure_count >= threshold:
        return False, True, "permanent_playwright"

    # Rule 2: Already failed today (no retry same day)
    # NOTE: Must check last_failure_date, NOT last_attempt_date
    # last_attempt_date is set on BOTH success and failure, so checking it would
    # incorrectly block retries after a successful reset
    last_failure_date = company_config.get('last_redirect_failure_date')
    if last_failure_date == today_iso:
        return False, True, "failed_today_use_playwright"

    # Rule 3: Allowed to try redirect
    return True, False, "allowed"


def should_route_to_playwright(
    company_config: Dict[str, Any],
    redirect_failed: bool,
    today_iso: str
) -> bool:
    """
    Determine if should route to Playwright (used after redirect attempt).

    Rules:
    - If redirect_strategy == "playwright_permanent" → True
    - If redirect_failed == True → True
    - If last_failure_date == today → True (already failed today)
    - Otherwise → False

    Args:
        company_config: Company configuration from DynamoDB
        redirect_failed: Whether redirect just failed
        today_iso: Today's date in YYYY-MM-DD format

    Returns:
        bool: True if should route to Playwright
    """
    redirect_strategy = company_config.get('redirect_strategy', 'redirect_first')
    last_failure_date = company_config.get('last_redirect_failure_date')

    # Check all routing conditions
    if redirect_strategy == 'playwright_permanent':
        return True

    if redirect_failed:
        return True

    if last_failure_date == today_iso:
        return True

    return False


def update_redirect_tracking(
    ticker: str,
    success: bool,
    companies_table: Any,
    today_iso: str
) -> None:
    """
    Update redirect tracking in DynamoDB (circuit breaker state).

    On success:
    - Reset failure_count to 0
    - Set redirect_strategy to "redirect_first"

    On failure (max 1 per day):
    - If last_failure_date != today: Increment failure_count
    - Update last_failure_date to today
    - If failure_count >= threshold: Set redirect_strategy to "playwright_permanent"

    Always:
    - Update last_attempt_date to today

    Args:
        ticker: Company ticker
        success: Whether redirect succeeded
        companies_table: DynamoDB table resource
        today_iso: Today's date in YYYY-MM-DD format
    """
    try:
        if success:
            # Success → Reset circuit breaker
            companies_table.update_item(
                Key={'ticker': ticker},
                UpdateExpression="""
                    SET redirect_failure_count = :zero,
                        redirect_strategy = :redirect_first,
                        last_redirect_attempt_date = :today
                """,
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':redirect_first': 'redirect_first',
                    ':today': today_iso
                }
            )
            logger.info(f"✅ Circuit breaker RESET for {ticker} (redirect succeeded)")

        else:
            # Failure → Update circuit breaker (max 1 count per day)
            # First, get current state to check if we should increment
            response = companies_table.get_item(Key={'ticker': ticker})
            company = response.get('Item', {})

            last_failure_date = company.get('last_redirect_failure_date')
            current_count = int(company.get('redirect_failure_count', 0) or 0)
            threshold = int(company.get('redirect_failure_threshold', 3) or 3)

            # Only increment if this is first failure today
            new_count = current_count + 1 if last_failure_date != today_iso else current_count

            # Determine new strategy
            new_strategy = 'playwright_permanent' if new_count >= threshold else 'redirect_first'

            # Update DynamoDB
            companies_table.update_item(
                Key={'ticker': ticker},
                UpdateExpression="""
                    SET redirect_failure_count = :count,
                        last_redirect_failure_date = :today,
                        last_redirect_attempt_date = :today,
                        redirect_strategy = :strategy
                """,
                ExpressionAttributeValues={
                    ':count': new_count,
                    ':today': today_iso,
                    ':strategy': new_strategy
                }
            )

            if new_strategy == 'playwright_permanent':
                logger.warning(
                    f"⚠️  Circuit breaker ACTIVATED for {ticker} "
                    f"({new_count} failures, threshold {threshold}) - "
                    f"Permanently routing to Playwright"
                )
            else:
                logger.info(
                    f"❌ Redirect failure recorded for {ticker} "
                    f"({new_count}/{threshold} failures)"
                )

    except Exception as e:
        # Non-critical - log but don't fail email processing
        logger.error(f"Failed to update redirect tracking for {ticker} (non-critical): {e}")


def get_redirect_tracking_status(company_config: Dict[str, Any]) -> str:
    """
    Get human-readable status for logging.

    Args:
        company_config: Company configuration from DynamoDB

    Returns:
        str: Status description
    """
    failure_count = int(company_config.get('redirect_failure_count', 0) or 0)
    redirect_strategy = company_config.get('redirect_strategy', 'redirect_first')
    last_attempt = company_config.get('last_redirect_attempt_date', 'never')
    last_failure = company_config.get('last_redirect_failure_date', 'never')
    threshold = int(company_config.get('redirect_failure_threshold', 3) or 3)

    if redirect_strategy == 'playwright_permanent':
        return f"Circuit breaker ACTIVE ({failure_count}/{threshold} failures, permanently using Playwright)"
    elif failure_count > 0:
        return f"Circuit breaker tracking ({failure_count}/{threshold} failures, last: {last_failure})"
    else:
        return "Circuit breaker inactive (no failures)"
