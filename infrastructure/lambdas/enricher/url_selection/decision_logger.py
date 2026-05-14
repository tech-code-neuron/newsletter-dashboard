"""
Decision Logger - Structured Logging for URL Selection
======================================================
Single Responsibility: Log all URL selection decisions for analysis

Logs all candidate URLs, their scores, signals, and which was selected.
Enables debugging, model tuning, and accuracy measurement over time.

Retention: 180 days in CloudWatch Logs
"""

import json
import logging
from datetime import datetime, timezone

from url_selection.detector import is_landing_page, is_utility_page, get_path_depth
from url_selection.extractor import extract_significant_words
from config.constants import (
    SCORE_SUBJECT_MATCH,
    SCORE_PATH_DEPTH,
    PENALTY_LANDING_PAGE,
    PENALTY_DB_MATCH,
    PENALTY_UTILITY_PAGE
)

logger = logging.getLogger()


def log_url_selection_decision(
    ticker,
    email_subject,
    candidate_urls_with_scores,
    selected_url,
    company,
    selection_method='email_smart_scoring'
):
    """
    Log URL selection decision with all scoring details

    This creates a structured JSON log entry that can be queried in CloudWatch Logs Insights
    to analyze model performance, debug incorrect selections, and tune scoring weights.

    Args:
        ticker: Company ticker (e.g., "RHP")
        email_subject: Email subject line
        candidate_urls_with_scores: List of (url, score) tuples from scoring
        selected_url: The URL that was selected
        company: Company config dict (for context)
        selection_method: How URL was selected (default: email_smart_scoring)

    Returns:
        dict: The decision log (also logged to CloudWatch)
    """
    # Build detailed candidate list with all signals
    candidates_detail = []
    for url, score in candidate_urls_with_scores:
        # Get all signals for this URL
        subject_words = extract_significant_words(email_subject)
        subject_matches = sum(1 for word in subject_words if word in url.lower())
        path_depth = get_path_depth(url)
        is_landing = is_landing_page(url)
        is_utility = is_utility_page(url)

        # Check if exact DB match (if press_release_url available)
        press_release_url = company.get('press_release_url', '')
        is_db_match = bool(press_release_url and url.rstrip('/') == press_release_url.rstrip('/'))

        # Calculate contribution of each signal to the score
        signal_contributions = {
            'subject_matches': subject_matches * SCORE_SUBJECT_MATCH,
            'path_depth': path_depth * SCORE_PATH_DEPTH,
            'landing_page_penalty': PENALTY_LANDING_PAGE if is_landing else 0,
            'db_match_penalty': PENALTY_DB_MATCH if is_db_match else 0,
            'utility_page_penalty': PENALTY_UTILITY_PAGE if is_utility else 0
        }

        candidates_detail.append({
            'url': url[:100],  # Truncate for log size
            'score': score,
            'selected': (url == selected_url),
            'signals': {
                'subject_matches_count': subject_matches,
                'path_depth': path_depth,
                'is_landing_page': is_landing,
                'is_db_match': is_db_match,
                'is_utility_page': is_utility
            },
            'signal_contributions': signal_contributions
        })

    # Sort by score (descending) for easier reading
    candidates_detail.sort(key=lambda x: x['score'], reverse=True)

    # Build decision log
    decision_log = {
        'event_type': 'url_selection_decision',
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
        'ticker': ticker,
        'email_subject': email_subject[:100],  # Truncate for privacy/size

        # Model configuration
        'model_version': 'v1.0-landing-page-detection-with-db-penalty',
        'scoring_weights': {
            'subject_match': SCORE_SUBJECT_MATCH,
            'path_depth': SCORE_PATH_DEPTH,
            'landing_page_penalty': PENALTY_LANDING_PAGE,
            'db_match_penalty': PENALTY_DB_MATCH,
            'utility_page_penalty': PENALTY_UTILITY_PAGE
        },

        # Candidate URLs with all details
        'candidate_urls': candidates_detail,

        # Selection outcome
        'outcome': {
            'selected_url': selected_url[:100] if selected_url else None,
            'selection_method': selection_method,
            'num_candidates': len(candidate_urls_with_scores),
            'score_spread': max(s for _, s in candidate_urls_with_scores) - min(s for _, s in candidate_urls_with_scores) if candidate_urls_with_scores else 0,
            'winning_score': next((s for u, s in candidate_urls_with_scores if u == selected_url), None)
        },

        # Company context
        'company_context': {
            'has_press_release_url': bool(company.get('press_release_url')),
            'has_ir_domain': bool(company.get('ir_domain')),
            'url_construction_method': company.get('url_construction_method', 'none')
        }
    }

    # Log as structured JSON for CloudWatch Logs Insights
    logger.info(json.dumps(decision_log))

    return decision_log


def get_decision_summary_stats(decision_log):
    """
    Get quick summary stats from a decision log (for debugging)

    Args:
        decision_log: Decision log dict

    Returns:
        str: Human-readable summary
    """
    outcome = decision_log['outcome']
    candidates = decision_log['candidate_urls']

    summary = f"""
    Ticker: {decision_log['ticker']}
    Candidates: {outcome['num_candidates']}
    Score Spread: {outcome['score_spread']}
    Winner Score: {outcome['winning_score']}

    Top 3 URLs:
    """

    for i, candidate in enumerate(candidates[:3], 1):
        marker = "✓ SELECTED" if candidate['selected'] else ""
        summary += f"\n  {i}. Score {candidate['score']:4d} {marker}"
        summary += f"\n     URL: {candidate['url'][:60]}..."
        summary += f"\n     Signals: subject={candidate['signals']['subject_matches_count']}, "
        summary += f"depth={candidate['signals']['path_depth']}, "
        summary += f"landing={candidate['signals']['is_landing_page']}"

    return summary
