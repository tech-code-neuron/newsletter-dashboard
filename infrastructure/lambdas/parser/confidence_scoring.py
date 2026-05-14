"""
Confidence Scoring - Multi-Signal Company Matching
===================================================
Bloomberg/FactSet-style confidence scoring with multiple signals

SOLID Principles:
- Strategy Pattern: Each signal is a separate class
- Single Responsibility: Each signal computes one type of confidence
- Open/Closed: Add new signals without modifying existing code

Author: Claude Code
Date: 2026-03-11
"""

import re
from typing import List, Dict, Optional, Tuple
from company_matching import normalize_company_name


class MatchSignal:
    """Base class for matching signals"""

    def score(self, email_metadata: Dict, company: Dict) -> float:
        """
        Compute confidence score for this signal

        Args:
            email_metadata: {sender_name, sender_domain, subject, urls}
            company: Company dict from DynamoDB

        Returns:
            float: Confidence score (0-100)
        """
        raise NotImplementedError


class DomainMatchSignal(MatchSignal):
    """
    Domain Match Signal: 90-100% confidence

    - Exact company domain: 100%
    - IR platform + name match: 95%
    - Third-party domain + name match: 90%
    """

    THIRD_PARTY_DOMAINS = {
        'q4inc.com', 'q4web.com', 'em.equisolve.com',
        'notification.gcs-web.com', 'alert.gcs-web.com',
        'ct.sendgrid.net'
    }

    def score(self, email_metadata: Dict, company: Dict) -> float:
        sender_domain = email_metadata.get('sender_domain', '').lower()
        if not sender_domain:
            return 0.0

        # Get company domains
        email_domain = company.get('email_domain', '').lower()
        ir_domain = company.get('ir_domain', '').lower()
        pr_domain = company.get('pr_url_domain', '').lower()
        all_domains = [d.lower() for d in company.get('all_domains', [])]

        # Exact email domain match: 100%
        if sender_domain == email_domain:
            return 100.0

        # Exact IR/PR domain match: 100%
        if sender_domain in [ir_domain, pr_domain]:
            return 100.0

        # Any known domain match: 100%
        if sender_domain in all_domains:
            return 100.0

        # Subdomain match (e.g., investors.foo.com matches foo.com)
        for domain in [email_domain, ir_domain, pr_domain] + all_domains:
            if domain and (sender_domain.endswith(f'.{domain}') or domain.endswith(f'.{sender_domain}')):
                return 95.0

        # Third-party domain + name match required
        if any(sender_domain.endswith(tpd) for tpd in self.THIRD_PARTY_DOMAINS):
            # Check if sender name matches company
            sender_name = email_metadata.get('sender_name', '')
            if sender_name:
                name_score = ExactNameMatchSignal().score(email_metadata, company)
                if name_score > 70:
                    return 90.0  # Third-party + name = high confidence

        return 0.0


class ExactNameMatchSignal(MatchSignal):
    """
    Exact Name Match Signal: 85% confidence

    Normalized sender name exactly matches normalized_name or name_variations
    """

    def score(self, email_metadata: Dict, company: Dict) -> float:
        sender_name = email_metadata.get('sender_name', '')
        if not sender_name:
            return 0.0

        normalized_sender = normalize_company_name(sender_name)
        if not normalized_sender:
            return 0.0

        # Try exact match on normalized_name (backward compatible)
        company_normalized = company.get('normalized_name', '')
        if normalized_sender == company_normalized:
            return 85.0

        # Try name variations (if available)
        name_variations = company.get('name_variations', [])
        for variation in name_variations:
            if normalized_sender == variation.get('normalized', ''):
                # Higher confidence for more frequent variations
                count = variation.get('count', 1)
                confidence = min(85.0 + (count // 10), 95.0)  # Cap at 95%
                return confidence

        return 0.0


class PartialNameMatchSignal(MatchSignal):
    """
    Partial Name Match Signal: 60-75% confidence

    - Containment: 75%
    - Word overlap > 80%: 70%
    - Word overlap > 60%: 65%
    """

    def score(self, email_metadata: Dict, company: Dict) -> float:
        sender_name = email_metadata.get('sender_name', '')
        if not sender_name:
            return 0.0

        normalized_sender = normalize_company_name(sender_name)
        if not normalized_sender:
            return 0.0

        # Get company names
        company_normalized = company.get('normalized_name', '')
        company_name = normalize_company_name(company.get('company_name', ''))

        # Check containment (one is substring of other)
        if company_normalized in normalized_sender or normalized_sender in company_normalized:
            return 75.0
        if company_name in normalized_sender or normalized_sender in company_name:
            return 75.0

        # Check name variations for containment
        name_variations = company.get('name_variations', [])
        for variation in name_variations:
            var_normalized = variation.get('normalized', '')
            if var_normalized in normalized_sender or normalized_sender in var_normalized:
                return 75.0

        # Word overlap
        sender_words = set(normalized_sender.split())
        company_words = set(company_normalized.split())

        if not sender_words or not company_words:
            return 0.0

        overlap = len(sender_words & company_words) / min(len(sender_words), len(company_words))

        if overlap > 0.8:
            return 70.0
        elif overlap > 0.6:
            return 65.0

        return 0.0


class HistoricalPatternSignal(MatchSignal):
    """
    Historical Pattern Signal: 70-90% confidence

    - 10+ successful matches: 90%
    - 5-9 matches: 80%
    - 2-4 matches: 70%
    - 1 match: 60%
    """

    def score(self, email_metadata: Dict, company: Dict) -> float:
        sender_domain = email_metadata.get('sender_domain', '')
        if not sender_domain:
            return 0.0

        # Get match history
        match_history = company.get('match_history', {})
        sender_domains = match_history.get('sender_domains', {})

        # Check if this sender domain has matched before
        match_count = sender_domains.get(sender_domain, 0)

        if match_count >= 10:
            return 90.0
        elif match_count >= 5:
            return 80.0
        elif match_count >= 2:
            return 70.0
        elif match_count == 1:
            return 60.0

        return 0.0


class TickerMentionSignal(MatchSignal):
    """
    Ticker Mention Signal: 40-60% confidence

    - Ticker in subject: 60%
    - Ticker in sender name: 50%
    """

    def score(self, email_metadata: Dict, company: Dict) -> float:
        ticker = company.get('ticker', '').upper()
        if not ticker or len(ticker) < 2:
            return 0.0

        subject = email_metadata.get('subject', '').upper()
        sender_name = email_metadata.get('sender_name', '').upper()

        # Exact ticker mention in subject (word boundary)
        if re.search(rf'\b{ticker}\b', subject):
            return 60.0

        # Ticker in sender name
        if re.search(rf'\b{ticker}\b', sender_name):
            return 50.0

        return 0.0


class ConfidenceScorer:
    """
    Confidence Scorer - Combines multiple signals

    Strategy: Use MAXIMUM confidence from all signals
    Rationale: If ANY signal is highly confident, it's a match
    """

    def __init__(self, strategy='maximum'):
        """
        Args:
            strategy: 'maximum' or 'weighted_average'
        """
        self.strategy = strategy
        self.signals = [
            DomainMatchSignal(),
            ExactNameMatchSignal(),
            PartialNameMatchSignal(),
            HistoricalPatternSignal(),
            TickerMentionSignal()
        ]

    def compute_confidence(
        self,
        email_metadata: Dict,
        company: Dict
    ) -> Tuple[float, str, Dict[str, float]]:
        """
        Compute confidence score for email-company match

        Args:
            email_metadata: {sender_name, sender_domain, subject, urls}
            company: Company dict from DynamoDB

        Returns:
            Tuple of (confidence, primary_signal, all_scores)
        """
        # Compute all signal scores
        scores = {}
        for signal in self.signals:
            signal_name = signal.__class__.__name__
            scores[signal_name] = signal.score(email_metadata, company)

        # Combine scores based on strategy
        if self.strategy == 'maximum':
            confidence = max(scores.values()) if scores else 0.0
            primary_signal = max(scores.items(), key=lambda x: x[1])[0] if scores else 'None'
        else:  # weighted_average
            weights = [0.5, 0.3, 0.1, 0.05, 0.05]  # Domain, ExactName, PartialName, Historical, Ticker
            weighted = sum(s * w for s, w in zip(scores.values(), weights))
            confidence = min(weighted, 100.0)
            primary_signal = 'WeightedAverage'

        return confidence, primary_signal, scores

    def match_with_confidence(
        self,
        email_metadata: Dict,
        companies: List[Dict],
        threshold: float = 70.0
    ) -> Optional[Tuple[Dict, float, str]]:
        """
        Find best matching company with confidence score

        Args:
            email_metadata: Email metadata dict
            companies: List of company dicts from DynamoDB
            threshold: Minimum confidence for auto-match (default: 70%)

        Returns:
            Tuple of (company, confidence, primary_signal) or None
        """
        best_match = None
        best_confidence = 0.0
        best_signal = None

        for company in companies:
            confidence, primary_signal, _ = self.compute_confidence(email_metadata, company)

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = company
                best_signal = primary_signal

        # Return match if above threshold
        if best_confidence >= threshold:
            return (best_match, best_confidence, best_signal)

        return None


# Confidence thresholds
CONFIDENCE_AUTO_MATCH = 70.0  # Auto-match threshold
CONFIDENCE_MANUAL_REVIEW = 50.0  # Manual review queue
