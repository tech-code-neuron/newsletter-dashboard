"""
Conservative Company Matcher
============================
Uses confidence scoring as fallback with strict constraints:
- Threshold: 75% (filters out weak matches)
- Safe signals only: Domain + Containment matching
- Excludes: Word overlap, ticker mentions, historical patterns without name

SOLID Principles:
- Single Responsibility: Only handles fallback matching when GSI fails
- Strategy Pattern: Uses DomainMatchSignal + Containment logic
- No False Positives: High threshold, conservative signals only

Author: Claude Code
Date: 2026-03-16
"""

import logging
from typing import Dict, List, Optional, Tuple
from confidence_scoring import DomainMatchSignal
from company_matching import normalize_company_name

logger = logging.getLogger()


class ConservativeMatcher:
    """
    Fallback matcher for GSI failures
    Uses only high-precision signals to minimize false positives
    """

    def __init__(self, threshold=75.0):
        """
        Initialize conservative matcher

        Args:
            threshold: Minimum confidence score (default: 75.0)
        """
        self.threshold = threshold
        self.domain_signal = DomainMatchSignal()

    def match(self, email_metadata: Dict, companies: List[Dict]) -> Tuple[Optional[Dict], float, Optional[str]]:
        """
        Find best match using conservative signals

        Args:
            email_metadata: {sender_name, sender_domain, subject, urls, from}
            companies: List of company dicts from DynamoDB

        Returns:
            Tuple of (company, confidence, signal_name) or (None, 0.0, None)
        """
        best_match = None
        best_confidence = 0.0
        best_signal = None

        for company in companies:
            # Try domain matching first (90-100%)
            domain_score = self.domain_signal.score(email_metadata, company)
            if domain_score >= self.threshold:
                if domain_score > best_confidence:
                    best_match = company
                    best_confidence = domain_score
                    best_signal = 'DomainMatch'

            # Try partial name matching (containment only - 75%)
            partial_score = self._containment_only_score(email_metadata, company)
            if partial_score >= self.threshold:
                if partial_score > best_confidence:
                    best_match = company
                    best_confidence = partial_score
                    best_signal = 'ContainmentMatch'

        if best_match:
            return (best_match, best_confidence, best_signal)
        return (None, 0.0, None)

    def _containment_only_score(self, email_metadata: Dict, company: Dict) -> float:
        """
        Containment matching with length-based scoring.
        Longer matches = more specific = higher scores.

        Score ranges:
            - Exact (unnormalized) match in subject: 85-90
            - Normalized match in subject: 75-84 (based on length)
            - Sender containment: 75-84 (based on length)

        Examples:
            "Diversified Healthcare Trust" exact in subject → 86.3
            "Healthcare Realty Trust" normalized only → 78.3
            Longer/more specific matches win.

        Args:
            email_metadata: {sender_name, subject, ...}
            company: Company dict with company_name, normalized_name

        Returns:
            float: Score 75-90 for match, 0.0 for no match
        """
        sender_name = email_metadata.get('sender_name', '')
        subject = email_metadata.get('subject', '')

        # Get company names
        full_company_name = company.get('company_name', '').lower().strip()
        company_normalized = company.get('normalized_name', '')
        normalized_name = normalize_company_name(company.get('company_name', ''))

        subject_lower = subject.lower() if subject else ''
        normalized_subject = normalize_company_name(subject) if subject else ''

        # PASS 1: Exact (unnormalized) containment in subject - highest confidence (85-90)
        if full_company_name and subject_lower and full_company_name in subject_lower:
            coverage = len(full_company_name) / len(subject_lower)
            score = 85.0 + (coverage * 5.0)
            score = min(score, 90.0)
            logger.debug(f"Exact containment: '{full_company_name}' in subject → {score:.1f}")
            return score

        # PASS 2: Normalized containment in subject - with length bonus (75-84)
        if normalized_subject:
            match_name = company_normalized or normalized_name
            if match_name and match_name in normalized_subject:
                length_bonus = min(len(match_name) / 3, 9.0)
                score = 75.0 + length_bonus
                logger.debug(f"Normalized containment: '{match_name}' ({len(match_name)} chars) → {score:.1f}")
                return score

        # PASS 3: Sender containment - with length scoring (75-84)
        if sender_name:
            normalized_sender = normalize_company_name(sender_name)
            if normalized_sender:
                match_name = company_normalized or normalized_name
                if match_name and (match_name in normalized_sender or normalized_sender in match_name):
                    length_bonus = min(len(match_name) / 3, 9.0)
                    score = 75.0 + length_bonus
                    logger.debug(f"Sender containment: '{match_name}' → {score:.1f}")
                    return score

        # PASS 4: Name variations (75-84)
        name_variations = company.get('name_variations', [])
        for variation in name_variations:
            var_normalized = variation.get('normalized', '')
            if var_normalized:
                # Check against subject
                if normalized_subject and var_normalized in normalized_subject:
                    length_bonus = min(len(var_normalized) / 3, 9.0)
                    score = 75.0 + length_bonus
                    logger.debug(f"Subject containment (variation): '{var_normalized}' → {score:.1f}")
                    return score
                # Check against sender
                if sender_name:
                    normalized_sender = normalize_company_name(sender_name)
                    if normalized_sender and (var_normalized in normalized_sender or normalized_sender in var_normalized):
                        length_bonus = min(len(var_normalized) / 3, 9.0)
                        score = 75.0 + length_bonus
                        logger.debug(f"Sender containment (variation): '{var_normalized}' → {score:.1f}")
                        return score

        return 0.0
