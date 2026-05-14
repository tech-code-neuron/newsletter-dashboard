"""
Press release categorization using Claude API
"""
import os
from anthropic import Anthropic
from core.models import get_session, PressRelease, Company
from datetime import datetime
import logging
import json
from utils.json_utils import extract_json_from_markdown

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PressReleaseCategorizer:
    """Categorize press releases using Claude"""
    
    # Category priorities (order matters for newsletter)
    CATEGORIES = [
        'M&A',
        'Property Transactions',
        'Equity Offerings',
        'Debt Offerings',
        'Credit Facilities',
        'Board Changes',
        'Personnel Changes',
        'Earnings',
        'Dividends',
        'Conference Call',
        'Other'
    ]
    
    # Breaking news categories (for 9am brief)
    BREAKING_CATEGORIES = ['M&A', 'Equity Offerings', 'Debt Offerings']

    # API configuration
    DEFAULT_MODEL = "claude-sonnet-4-20250514"  # Claude model for categorization
    MAX_TOKENS = 1000  # Claude API max tokens for categorization

    def __init__(self, api_key=None):
        if api_key is None:
            api_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found. Set it in .env file or pass to constructor")
        
        self.client = Anthropic(api_key=api_key)
        self.db_session = get_session()
    
    def categorize_press_release(self, press_release):
        """
        Categorize a single press release using Claude
        Returns dict with category, summary, is_breaking
        """
        if not press_release.content:
            logger.warning(f"No content for press release {press_release.id}")
            return None
        
        # Build the prompt
        prompt = f"""You are analyzing a company press release. 

Categories (in priority order):
1. M&A - Mergers, acquisitions, company sales
2. Property Transactions - Property acquisitions, dispositions, development
3. Equity Offerings - Stock offerings, ATM programs, equity raises
4. Debt Offerings - Bond issuances, note offerings
5. Credit Facilities - Credit lines, term loans, refinancing
6. Board Changes - Board member appointments, resignations
7. Personnel Changes - Executive hires, departures, promotions
8. Earnings - Quarterly/annual results, earnings releases
9. Dividends - Dividend announcements, changes, special dividends
10. Conference Call - Earnings call announcements (often combined with earnings)
11. Other - Anything else

Press Release Title:
{press_release.title}

Press Release Content:
{press_release.content[:3000]}  

Tasks:
1. Select ONE primary category from the list above
2. If it's an earnings release that also announces a conference call, categorize as "Earnings" (not Conference Call)
3. Determine if this is "breaking news" (M&A, Equity Offerings, or Debt Offerings)
4. Write a 1-2 sentence professional summary suitable for executives

Respond in this exact JSON format:
{{
    "category": "category name",
    "is_breaking": true or false,
    "summary": "your concise summary here"
}}"""
        
        try:
            # Call Claude API
            message = self.client.messages.create(
                model=self.DEFAULT_MODEL,
                max_tokens=self.MAX_TOKENS,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract response
            response_text = message.content[0].text.strip()

            # Parse JSON response using utility (handles markdown code fences)
            json_str = extract_json_from_markdown(response_text)
            result = json.loads(json_str)
            
            # Validate category
            if result['category'] not in self.CATEGORIES:
                logger.warning(f"Invalid category '{result['category']}', defaulting to 'Other'")
                result['category'] = 'Other'
            
            return result
            
        except Exception as e:
            logger.error(f"Error categorizing press release {press_release.id}: {e}")
            return {
                'category': 'Other',
                'is_breaking': False,
                'summary': press_release.title
            }
    
    def categorize_uncategorized(self, limit=None):
        """
        Categorize all press releases that don't have a category yet
        """
        # Find uncategorized releases
        query = self.db_session.query(PressRelease).filter(
            PressRelease.category.is_(None)
        ).order_by(PressRelease.published_date.desc())
        
        if limit:
            query = query.limit(limit)
        
        uncategorized = query.all()
        
        if not uncategorized:
            logger.info("No uncategorized press releases found")
            return 0
        
        logger.info(f"Categorizing {len(uncategorized)} press releases...")
        
        success_count = 0
        
        for i, pr in enumerate(uncategorized, 1):
            company = pr.company
            logger.info(f"\n[{i}/{len(uncategorized)}] {company.ticker}: {pr.title[:60]}")
            
            result = self.categorize_press_release(pr)
            
            if result:
                pr.category = result['category']
                pr.is_breaking = result.get('is_breaking', False)
                pr.summary = result.get('summary', pr.title)
                
                self.db_session.commit()
                
                logger.info(f"  → Category: {pr.category}")
                logger.info(f"  → Breaking: {pr.is_breaking}")
                logger.info(f"  → Summary: {pr.summary[:100]}")
                
                success_count += 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Categorization complete!")
        logger.info(f"Successfully categorized: {success_count}/{len(uncategorized)}")
        logger.info(f"{'='*60}")
        
        return success_count
    
    def recategorize_by_id(self, press_release_id):
        """
        Re-categorize a specific press release by ID
        Useful for fixing categorization errors
        """
        pr = self.db_session.query(PressRelease).get(press_release_id)
        
        if not pr:
            logger.error(f"Press release {press_release_id} not found")
            return False
        
        logger.info(f"Re-categorizing: {pr.company.ticker} - {pr.title[:60]}")
        
        result = self.categorize_press_release(pr)
        
        if result:
            pr.category = result['category']
            pr.is_breaking = result.get('is_breaking', False)
            pr.summary = result.get('summary', pr.title)
            pr.manually_edited = False  # Reset manual edit flag
            
            self.db_session.commit()
            
            logger.info(f"  → New category: {pr.category}")
            return True
        
        return False
    
    def get_categorization_stats(self):
        """
        Get statistics on categorized press releases
        """
        from sqlalchemy import func
        
        stats = self.db_session.query(
            PressRelease.category,
            func.count(PressRelease.id).label('count')
        ).group_by(PressRelease.category).all()
        
        total = self.db_session.query(PressRelease).count()
        uncategorized = self.db_session.query(PressRelease).filter(
            PressRelease.category.is_(None)
        ).count()
        
        logger.info(f"\nPress Release Statistics:")
        logger.info(f"Total: {total}")
        logger.info(f"Uncategorized: {uncategorized}")
        logger.info(f"\nBy Category:")
        
        for category, count in sorted(stats, key=lambda x: x[1], reverse=True):
            category_name = category or "Uncategorized"
            logger.info(f"  {category_name}: {count}")
        
        return stats
    
    def close(self):
        """Clean up resources"""
        self.db_session.close()


if __name__ == "__main__":
    # Load API key from environment
    from dotenv import load_dotenv
    load_dotenv()
    
    categorizer = PressReleaseCategorizer()
    
    # Show current stats
    categorizer.get_categorization_stats()
    
    # Categorize uncategorized releases
    categorizer.categorize_uncategorized()
    
    # Show updated stats
    categorizer.get_categorization_stats()
    
    categorizer.close()
