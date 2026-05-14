"""
Prospectus Processor Lambda (repurposed from 8K-Processor)

Processes 424/FWP prospectus filings:
- Fetch document from SEC
- Extract offering details with AI
- Save structured data to DynamoDB
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Tuple
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import boto3
from shared.dynamodb_update_builder import DynamoDBUpdateBuilder
from shared.timestamp_utils import get_current_timestamp_utc
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# Tables
FILINGS_TABLE = os.environ.get('FILINGS_TABLE', 'reitsheet-8k-disclosures')

# SEC
SEC_USER_AGENT = "PressReleasePipeline/1.0 (contact@your-domain.comm)"
SEC_RATE_LIMIT_DELAY = 0.15

# Eastern timezone for SEC timestamp conversion
ET_TZ = ZoneInfo('America/New_York')


def safe_decimal(value) -> Optional[Decimal]:
    """
    Convert value to Decimal, handling currency formatting and arrays.

    Handles edge cases from AI extraction:
    - Arrays (multi-tranche deals): [4.25, 4.9] → takes first value
    - Currency strings: "$500,000,000" → 500000000
    - Percentages: "4.25%" → 4.25
    - Invalid strings: "N/A", "TBD" → None
    """
    if value is None:
        return None
    # Handle arrays - take first value (multi-tranche deals)
    if isinstance(value, list):
        value = value[0] if value else None
        if value is None:
            return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    # String handling
    s = str(value).strip()
    if not s or s.lower() in ('n/a', 'tbd', 'none', 'null', ''):
        return None
    # Remove currency symbols, commas, and percent signs
    s = re.sub(r'[$,%]', '', s)
    # Take first number if multiple present (e.g., "4.25 / 4.9")
    match = re.search(r'-?[\d.]+', s)
    if match:
        try:
            return Decimal(match.group())
        except InvalidOperation:
            return None
    return None


def convert_sec_timestamp_to_utc(sec_timestamp: str) -> str:
    """
    Convert SEC timestamp from ET (mislabeled as UTC) to proper UTC.

    SEC API returns timestamps like "2026-03-30T09:00:30.000Z" where the time
    is actually Eastern Time, not UTC. The .000Z suffix is misleading.

    Args:
        sec_timestamp: SEC format timestamp (e.g., "2026-03-30T09:00:30.000Z")

    Returns:
        Proper UTC ISO 8601 timestamp (e.g., "2026-03-30T13:00:30+00:00")
    """
    if not sec_timestamp:
        return ''

    # Strip the misleading .000Z suffix
    clean = sec_timestamp.replace('.000Z', '').replace('Z', '')

    # Parse as ET (the actual timezone)
    et_dt = datetime.fromisoformat(clean)
    et_dt = et_dt.replace(tzinfo=ET_TZ)

    # Convert to UTC
    utc_dt = et_dt.astimezone(timezone.utc)
    return utc_dt.isoformat()


def extract_acceptance_from_index_page(filing_url: str) -> str:
    """
    Extract acceptance timestamp from SEC filing index page as fallback.

    The index page contains (in ET timezone):
        <div class="infoHead">Accepted</div>
        <div class="info">2026-03-30 09:00:30</div>

    Converts ET to UTC for consistent database storage.

    Args:
        filing_url: SEC index page URL (e.g., .../0001104659-26-036513-index.htm)

    Returns:
        ISO 8601 UTC timestamp string, or empty string if extraction fails
    """
    headers = {"User-Agent": SEC_USER_AGENT}

    try:
        time.sleep(SEC_RATE_LIMIT_DELAY)
        response = requests.get(filing_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Parse: <div class="infoHead">Accepted</div>\s*<div class="info">YYYY-MM-DD HH:MM:SS</div>
        match = re.search(
            r'<div class="infoHead">Accepted</div>\s*<div class="info">(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})</div>',
            response.text
        )
        if match:
            date_str, time_str = match.group(1), match.group(2)

            # Parse as ET and convert to UTC
            et_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            et_dt = et_dt.replace(tzinfo=ET_TZ)
            utc_dt = et_dt.astimezone(timezone.utc)

            timestamp = utc_dt.isoformat()
            logger.info(f"Extracted acceptance timestamp: {date_str} {time_str} ET → {timestamp} UTC")
            return timestamp

        logger.warning(f"Could not find acceptance timestamp pattern in index page: {filing_url}")
        return ''

    except requests.RequestException as e:
        logger.error(f"Failed to fetch index page {filing_url}: {e}")
        return ''


class HTMLTextExtractor(HTMLParser):
    """Extract text from HTML."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_style = False
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        if tag == 'style':
            self.in_style = True
        elif tag == 'script':
            self.in_script = True
        elif tag in ('p', 'div', 'br', 'tr', 'li', 'td', 'th'):
            self.text_parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False
        elif tag == 'script':
            self.in_script = False

    def handle_data(self, data):
        if not self.in_style and not self.in_script:
            self.text_parts.append(data)

    def get_text(self) -> str:
        return ''.join(self.text_parts)


def fetch_prospectus_document(filing_url: str, doc_url: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch prospectus document from SEC EDGAR.

    Args:
        filing_url: Index page URL
        doc_url: Direct document URL (if known)

    Returns: (text_content, sec_document_url)
    """
    headers = {"User-Agent": SEC_USER_AGENT}

    try:
        # If we have direct doc URL, use it
        target_url = doc_url
        sec_document_url = doc_url

        if not target_url:
            # Fetch index page to find document
            response = requests.get(filing_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Find the main document link
            base_url = filing_url.rsplit('/', 1)[0]

            # Look for .htm files (excluding index files and exhibits)
            # SEC uses both absolute paths (/Archives/...) and relative paths
            patterns = [
                # Absolute paths (most common in new SEC pages)
                r'href="(/Archives/edgar/data/[^"]+\.htm)"',
                # Relative paths (legacy)
                r'href="([a-zA-Z0-9_-]+\.htm)"',
            ]

            # Skip files that look like exhibits (not the main prospectus)
            EXHIBIT_PATTERNS = [
                'waiver', 'amendment', 'exhibit', 'agreement',
                'consent', 'forbearance', 'covenant', 'modification',
                'certificate', 'opinion', 'power'
            ]

            for pattern in patterns:
                matches = re.findall(pattern, response.text, re.IGNORECASE)
                for match in matches:
                    filename_lower = match.lower()
                    # Skip index and summary files
                    if 'index' in filename_lower or 'FilingSummary' in match:
                        continue
                    # Skip exhibit-like files (waivers, amendments, etc.)
                    if any(pat in filename_lower for pat in EXHIBIT_PATTERNS):
                        logger.info(f"Skipping exhibit-like file: {match}")
                        continue
                    # Handle absolute vs relative paths
                    if match.startswith('/'):
                        target_url = f"https://www.sec.gov{match}"
                    else:
                        target_url = f"{base_url}/{match}"
                    sec_document_url = target_url
                    break
                if target_url:
                    break

        if not target_url:
            logger.warning(f"Could not find document in {filing_url}")
            return None, None

        logger.info(f"Fetching document: {target_url}")
        time.sleep(SEC_RATE_LIMIT_DELAY)

        doc_response = requests.get(target_url, headers=headers, timeout=60)
        doc_response.raise_for_status()

        # Extract text
        parser = HTMLTextExtractor()
        parser.feed(doc_response.text)
        text = parser.get_text()

        # Clean up
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        # Get first 15000 chars (prospectuses are long, key info usually upfront)
        text = text[:15000]

        return text.strip(), sec_document_url

    except Exception as e:
        logger.error(f"Failed to fetch prospectus: {e}")
        return None, None


def extract_offering_details(content: str, issuer_name: str, form_type: str) -> Dict:
    """
    Extract offering details from prospectus using AI.

    Returns dict with:
    - offering_type, security_type, principal_amount, principal_display
    - maturity_date, coupon_rate, pricing_date, price_per_share
    - use_of_proceeds, title, summary
    """

    prompt = f"""You are analyzing a prospectus filing for a REIT newsletter.

ISSUER: {issuer_name}
FORM TYPE: {form_type}

DOCUMENT CONTENT:
{content}

=== EXCLUSION FILTERS (CHECK FIRST) ===

Set skip_reason to a non-null string if ANY of these apply:

1. "10k_10q_update": Filing just incorporates 10-K/10-Q information
   INDICATORS:
   - "filed to update, amend, and supplement" with "Annual Report on Form 10-K"
   - "filed to update" with "Quarterly Report on Form 10-Q"
   - "This Prospectus Supplement is being filed to update" with periodic report
   - Primary purpose is incorporating periodic report, not announcing new offering

2. "8k_appendix": Filing attaches/incorporates an 8-K about non-offering events
   INDICATORS:
   - "attached to this Supplement our current report on Form 8-K"
   - "We have attached...Form 8-K" or "attaching...8-K"
   - "filed to incorporate by reference" an 8-K
   - Contains 8-K items: "ITEM 2.01" (property transactions) or "ITEM 8.01" (other events)
   - Primary content is 8-K text about property sales, NOT securities offerings
   - The 8-K discusses "completed the sale of" real estate
   - Contains "COMPLETION OF ACQUISITION OR DISPOSITION OF ASSETS"

3. "property_transaction": Filing about property sale/purchase, not securities
   INDICATORS:
   - "ITEM 2.01 COMPLETION OF ACQUISITION OR DISPOSITION OF ASSETS"
   - "completed the sale of" a property
   - "purchase and sale agreement" for real estate
   - About real estate transactions, not securities offerings
   - NO securities pricing, NO shares being offered in THIS supplement

4. "no_new_offering": No material new offering information
   INDICATORS:
   - Just a technical amendment with no deal terms
   - Sticker supplement with minor corrections only

5. "loan_modification": Loan waiver, amendment, or credit agreement exhibit
   INDICATORS:
   - "limited waiver" in document title or content
   - "waiver and amendment" to credit agreement
   - "forbearance agreement" or "forbearance period"
   - "loan modification agreement"
   - "waiver of covenant" or "covenant waiver"
   - "consent and waiver" for debt obligations
   - Document discusses loan/credit terms, NOT securities offering
   - File is an EXHIBIT to a prospectus, not the prospectus itself
   - Contains phrases like "credit facility", "term loan", "revolving credit"
     WITHOUT any securities offering terms

If skip_reason is set, return ONLY: {{"skip_reason": "<reason>"}}

=== OFFERING TYPE DETECTION (8 TYPES) ===

1. IPO (Initial Public Offering): First-time public offering
   INDICATORS:
   - "initial public offering" language
   - S-1 registration for company going public
   - First time shares offered to public
   - Title: "[Issuer] Prices Initial Public Offering of [X.X] Million Shares at $[Price] Per Share"

2. SECONDARY (Selling Shareholders Only): 100% secondary shares
   INDICATORS:
   - "selling stockholders" or "selling shareholders" are the ONLY sellers
   - Company receives NO proceeds
   - "The selling stockholders will receive all of the net proceeds"
   - Title: "[Issuer] to Offer [X.X] Million Shares on Behalf of Selling Shareholders"
   - Use "Offers" NOT "Issues" (company isn't issuing new shares)

3. PRIMARY_SECONDARY (Mixed): Both primary and secondary shares
   INDICATORS:
   - Company selling shares AND selling shareholders selling shares
   - Separate counts for primary vs secondary
   - Title: "[Issuer] to Offer [X.X] Million Primary and [Y.Y] Million Secondary Shares"

4. ATM (At-the-Market Program): Distribution agreement for ongoing sales
   INDICATORS:
   - "distribution agreement" or "equity distribution agreement"
   - "at-the-market" or "ATM"
   - "sales agent" (not underwriters)
   - "from time to time"

5. SHELF (Contingent/Shelf Issuance): Future possible issuance
   INDICATORS:
   - "may offer" or "may sell"
   - OP unit conversion or exchange filings
   - NO specific pricing

6. PRELIMINARY: Pricing terms TBD
   INDICATORS:
   - "[    ]" or blank placeholders
   - "preliminary prospectus supplement"

7. PRICED (Final Priced Primary Offering): Completed transaction
   INDICATORS:
   - Specific pricing date/settlement date
   - Exact price per share
   - Company is the seller (NOT selling shareholders)

8. REGISTRATION (S-1, S-11, 10-12B): Registration statement

=== SHARE COUNT FORMATTING (MANDATORY) ===

Format share counts as follows:
- >= 1,000,000: Round to 1 decimal place as "X.X Million Shares"
  Examples: 10,980,000 -> "11.0 Million Shares"
            1,170,000 -> "1.2 Million Shares"
            17,100,000 -> "17.1 Million Shares"
            42,000,000 -> "42.0 Million Shares"

- < 1,000,000: Show full amount with commas
  Examples: 152,905 -> "152,905 Shares"
            500,000 -> "500,000 Shares"

NEVER use more than 1 decimal place (wrong: "10.98 Million")
NEVER show full millions without "Million" (wrong: "17,100,000 Shares" if >= 1M)

=== TITLE GENERATION RULES ===

- IPO: "[Issuer] Prices Initial Public Offering of [X.X] Million Shares at $[Price] Per Share"
- SECONDARY: "[Issuer] to Offer [X.X] Million Shares on Behalf of Selling Shareholders"
- PRIMARY_SECONDARY: "[Issuer] to Offer [X.X] Million Primary and [Y.Y] Million Secondary Shares"
- ATM: "[Issuer] Establishes At-the-Market Program to Offer Up to $[Amount] of [Security]"
- SHELF: "[Issuer] to Offer Up to [X.X] Million [Security Type]"
- PRELIMINARY: "[Issuer] Launches Offering of [X.X] Million Shares"
- PRICED (Debt with rate, 1 tranche): "[Issuer] Prices $[Amount] Offering of [Rate]% Notes Due [Year]"
- PRICED (Debt with rate, 2 tranches): "[Issuer] Prices $[Amount1] Offering of [Rate1]% Notes Due [Year1] and $[Amount2] of [Rate2]% Notes Due [Year2]"
- PRICED (Debt with rate, 3+ tranches): "[Issuer] Prices Multi-Tranche Notes Offering"
- PRICED (Debt, rate missing, 1 maturity): "[Issuer] Launches Notes Due [Year]"
- PRICED (Debt, rate AND year missing): "[Issuer] Launches Notes Offering"
- PRICED (Debt, rate missing, 2 maturities): "[Issuer] Launches Notes Due [Year1] and [Year2]"
- PRICED (Debt, rate missing, 3+ maturities): "[Issuer] Launches Multi-Tranche Notes Offering"
- PRICED (Equity Primary): "[Issuer] Prices [X.X] Million Shares at $[Price] Per Share"
- REGISTRATION: "[Issuer] Registers Up to $[Amount] in Securities"

=== "FROM TIME TO TIME" RULE (MANDATORY) ===

If the cover page or offering description contains "from time to time", add "Up to" after "Offer" in the title.
This indicates shares may be sold over a period, not all at once.

- WITHOUT "from time to time": "[Issuer] to Offer 6.1 Million Shares on Behalf of Selling Shareholders"
- WITH "from time to time": "[Issuer] to Offer Up to 6.1 Million Shares on Behalf of Selling Shareholders"

This applies to SECONDARY, PRIMARY_SECONDARY, SHELF, and similar offering types where the amount represents a maximum.

Examples:
- IPO: "Janus Living, Inc. Prices Initial Public Offering of 42.0 Million Shares at $20.00 Per Share"
- SECONDARY (no "from time to time"): "Safehold Inc. to Offer 6.1 Million Shares on Behalf of Selling Shareholders"
- SECONDARY (with "from time to time"): "Safehold Inc. to Offer Up to 6.1 Million Shares on Behalf of Selling Shareholders"
- PRIMARY_SECONDARY: "Hudson Pacific Properties to Offer 17.1 Million Primary and 1.2 Million Secondary Shares"
- PRICED Primary: "NETSTREIT Corp. Prices 11.0 Million Shares at $19.00 Per Share"
- SHELF (small): "BXP, Inc. to Offer Up to 152,905 Shares of Common Stock"

=== FIELDS TO EXTRACT ===

1. SKIP_REASON: null, "10k_10q_update", "8k_appendix", "no_new_offering", "property_transaction", or "loan_modification"
2. OFFERING_TYPE: "ipo", "secondary", "primary_secondary", "atm", "shelf", "preliminary", "priced", or "registration"
3. IS_IPO: true/false
4. IS_FROM_TIME_TO_TIME: true if cover page contains "from time to time" (triggers "Up to" in title)
5. PRIMARY_SHARES: Number of primary shares (company issuing)
6. SECONDARY_SHARES: Number of secondary shares (selling shareholders)
7. PRIMARY_DISPLAY: Formatted primary shares (e.g., "17.1 Million Shares")
8. SECONDARY_DISPLAY: Formatted secondary shares (e.g., "1.2 Million Shares")
9. SECURITY_TYPE: e.g., "Common Stock", "Preferred Stock", "Notes", "Senior Notes"
10. PRINCIPAL_AMOUNT: Total offering size as number
11. PRINCIPAL_DISPLAY: Human-readable total (e.g., "11.0 Million Shares" or "$500 Million")
12. PRICE_PER_SHARE: Price per share as number (equity only)
13. PRICING_DATE: YYYY-MM-DD (if priced)
14. USE_OF_PROCEEDS: 1-2 sentences
15. TITLE: Following rules above (include "Up to" if is_from_time_to_time is true)
16. SUMMARY: 2-3 sentences
17. INTEREST_RATE: Coupon rate as number (debt only, e.g., 5.25). null if not specified or placeholder
18. MATURITY_YEARS: Array of maturity years (debt only, e.g., [2033] or [2033, 2035]). Empty array if not specified

Respond with JSON only (no markdown):

Example (equity):
{{
  "skip_reason": null,
  "offering_type": "priced",
  "is_ipo": false,
  "is_from_time_to_time": false,
  "primary_shares": 10980000,
  "secondary_shares": 0,
  "primary_display": "11.0 Million Shares",
  "secondary_display": null,
  "security_type": "Common Stock",
  "principal_amount": 10980000,
  "principal_display": "11.0 Million Shares",
  "price_per_share": 19.00,
  "pricing_date": "2026-02-13",
  "use_of_proceeds": "General corporate purposes and debt repayment.",
  "title": "NETSTREIT Corp. Prices 11.0 Million Shares at $19.00 Per Share",
  "summary": "NETSTREIT Corp. priced a public offering of 11.0 million shares at $19.00 per share.",
  "interest_rate": null,
  "maturity_years": []
}}

Example (debt with rate):
{{
  "skip_reason": null,
  "offering_type": "priced",
  "security_type": "Senior Notes",
  "principal_amount": 500000000,
  "principal_display": "$500 Million",
  "interest_rate": 5.25,
  "maturity_years": [2033],
  "title": "Realty Income Prices $500 Million Offering of 5.25% Notes Due 2033",
  "summary": "Realty Income priced $500 million of 5.25% senior notes due 2033."
}}

Example (debt, rate missing):
{{
  "skip_reason": null,
  "offering_type": "preliminary",
  "security_type": "Notes",
  "interest_rate": null,
  "maturity_years": [2033],
  "title": "Realty Income Launches Notes Due 2033",
  "summary": "Realty Income filed a preliminary prospectus for notes due 2033."
}}"""

    try:
        response = bedrock.invoke_model(
            modelId='amazon.nova-pro-v1:0',
            body=json.dumps({
                'inferenceConfig': {'maxTokens': 800},
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}]
            })
        )

        result = json.loads(response['body'].read())
        text = result.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')

        # Parse JSON (handle potential markdown code blocks)
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        data = json.loads(text)

        return {
            'skip_reason': data.get('skip_reason'),
            'offering_type': data.get('offering_type', 'priced'),
            'is_ipo': data.get('is_ipo', False),
            'is_from_time_to_time': data.get('is_from_time_to_time', False),
            'primary_shares': data.get('primary_shares'),
            'secondary_shares': data.get('secondary_shares'),
            'primary_display': data.get('primary_display'),
            'secondary_display': data.get('secondary_display'),
            'security_type': data.get('security_type', 'Securities'),
            'principal_amount': data.get('principal_amount'),
            'principal_display': data.get('principal_display', ''),
            'interest_rate': data.get('interest_rate'),
            'maturity_years': data.get('maturity_years', []),
            'pricing_date': data.get('pricing_date'),
            'price_per_share': data.get('price_per_share'),
            'use_of_proceeds': data.get('use_of_proceeds', ''),
            'title': data.get('title', f'{issuer_name} Prospectus Filing'),
            'summary': data.get('summary', '')
        }

    except Exception as e:
        logger.error(f"AI extraction failed: {e}")
        return {
            'skip_reason': None,
            'offering_type': 'priced',
            'is_ipo': False,
            'is_from_time_to_time': False,
            'primary_shares': None,
            'secondary_shares': None,
            'primary_display': None,
            'secondary_display': None,
            'security_type': 'Securities',
            'principal_amount': None,
            'principal_display': '',
            'interest_rate': None,
            'maturity_years': [],
            'pricing_date': None,
            'price_per_share': None,
            'use_of_proceeds': '',
            'title': f'{issuer_name} {form_type} Filing',
            'summary': 'See SEC document for details.'
        }


def save_prospectus(message: Dict, details: Dict, sec_url: str) -> bool:
    """Save prospectus filing to DynamoDB."""
    table = dynamodb.Table(FILINGS_TABLE)

    # Get acceptance timestamp with fallback chain (all converted to proper UTC):
    # 1. From SQS message (fetcher got it from SEC API - needs ET→UTC conversion)
    # 2. From SEC index page (if API had propagation delay - already returns UTC)
    # 3. Processing timestamp (last resort - already UTC)
    raw_acceptance = message.get('acceptance_datetime', '')
    if raw_acceptance:
        # SEC API timestamp is ET mislabeled as UTC - convert to proper UTC
        acceptance_dt = convert_sec_timestamp_to_utc(raw_acceptance)
        logger.info(f"Converted SEC timestamp: {raw_acceptance} → {acceptance_dt}")
    else:
        logger.warning(f"Empty acceptance_datetime for {message['ticker']} {message.get('form_type')} - trying index page fallback")
        acceptance_dt = extract_acceptance_from_index_page(message['filing_url'])

    if not acceptance_dt:
        # Final fallback: use processing timestamp (already UTC)
        acceptance_dt = get_current_timestamp_utc()
        logger.warning(f"Index page fallback failed for {message['ticker']} - using processing timestamp")

    item = {
        'filing_url': message['filing_url'],
        'ticker': message['ticker'],
        'issuer_cik': message.get('issuer_cik', ''),
        'issuer_name': message.get('issuer_name', ''),
        'issuer_type': message.get('issuer_type', 'reit'),
        'form_type': message.get('form_type', ''),
        'filing_date': message.get('filing_date', ''),

        # Offering details
        'offering_type': details.get('offering_type', 'priced'),
        'is_ipo': details.get('is_ipo', False),
        'is_from_time_to_time': details.get('is_from_time_to_time', False),
        'security_type': details.get('security_type', ''),
        'principal_display': details.get('principal_display', ''),
        'primary_display': details.get('primary_display'),
        'secondary_display': details.get('secondary_display'),
        'maturity_years': details.get('maturity_years', []),
        'pricing_date': details.get('pricing_date'),
        'use_of_proceeds': details.get('use_of_proceeds', ''),

        # AI summary
        'ai_summary_title': details.get('title', ''),
        'ai_summary_content': details.get('summary', ''),

        # Metadata
        'sec_document_url': sec_url,
        'sec_accepted_at': acceptance_dt,  # Proper UTC timestamp
        'first_seen_at': get_current_timestamp_utc(),  # Our processing timestamp
        'newsletter_status': 'ready'
    }

    # Handle numeric fields that need Decimal for DynamoDB
    # Use safe_decimal to handle arrays (multi-tranche deals), currency formatting, etc.
    if (val := safe_decimal(details.get('principal_amount'))):
        item['principal_amount'] = val
    if (val := safe_decimal(details.get('interest_rate'))):
        item['interest_rate'] = val
    if (val := safe_decimal(details.get('price_per_share'))):
        item['price_per_share'] = val
    if (val := safe_decimal(details.get('primary_shares'))):
        item['primary_shares'] = val
    if (val := safe_decimal(details.get('secondary_shares'))):
        item['secondary_shares'] = val

    # Remove None values and empty lists
    item = {k: v for k, v in item.items() if v is not None and v != []}

    try:
        # Check if item already exists (user may have modified status)
        filing_url = item['filing_url']
        try:
            existing = table.get_item(Key={'filing_url': filing_url}).get('Item')
        except Exception as e:
            logger.error(f"Error checking existing disclosure: {e}")
            existing = None

        if existing and existing.get('newsletter_status') != 'ready':
            # Item exists with user-modified status - preserve it
            logger.info(f"Preserving user-modified status '{existing['newsletter_status']}' for {filing_url[:60]}...")

            # Update only non-status fields
            updates = {k: v for k, v in item.items() if k != 'newsletter_status' and k != 'filing_url'}

            builder = DynamoDBUpdateBuilder(primary_key='filing_url')
            update_kwargs = builder.build(updates, remove_none=False)

            table.update_item(Key={'filing_url': filing_url}, **update_kwargs)
        else:
            # New item or status is still 'ready' - safe to overwrite
            table.put_item(Item=item)
            logger.info(f"Saved {message['ticker']} {message.get('form_type', '')}: {details.get('title', '')[:60]}...")

        return True
    except Exception as e:
        logger.error(f"Failed to save: {e}")
        return False


def find_matching_priced_fwp(ticker: str, security_type: str, principal_amount: float,
                             filing_date: str) -> Optional[Dict]:
    """
    Check if a matching priced FWP already exists for this deal.

    Match criteria:
    - Same ticker
    - Same security_type (e.g., "Senior Notes", "Common Stock")
    - Principal amount within 5%
    - Filed within 14 days before this filing
    - Both must be 'priced' offering_type

    Returns: Matching FWP item if found, None otherwise
    """
    from datetime import timedelta
    from boto3.dynamodb.conditions import Attr

    if not principal_amount:
        return None

    table = dynamodb.Table(FILINGS_TABLE)

    # Calculate date range (14 days before this filing)
    try:
        filing_dt = datetime.strptime(filing_date, '%Y-%m-%d')
        start_date = (filing_dt - timedelta(days=14)).strftime('%Y-%m-%d')
    except:
        return None

    # Scan for matching FWPs (table is small, scan is acceptable)
    try:
        response = table.scan(
            FilterExpression=Attr('ticker').eq(ticker) &
                            Attr('form_type').eq('FWP') &
                            Attr('offering_type').eq('priced') &
                            Attr('security_type').eq(security_type) &
                            Attr('filing_date').between(start_date, filing_date)
        )
    except Exception as e:
        logger.warning(f"FWP lookup failed: {e}")
        return None

    if not response.get('Items'):
        return None

    # Check principal amount match (within 5%)
    for item in response['Items']:
        item_amount = item.get('principal_amount')
        if item_amount:
            try:
                ratio = float(principal_amount) / float(item_amount)
                if 0.95 <= ratio <= 1.05:
                    return item
            except:
                continue

    return None


def process_filing(message: Dict) -> Dict:
    """Process a single prospectus filing."""
    ticker = message['ticker']
    filing_url = message['filing_url']
    doc_url = message.get('doc_url')
    form_type = message.get('form_type', '424B5')
    issuer_name = message.get('issuer_name', ticker)

    logger.info(f"Processing {ticker} {form_type}: {filing_url}")

    # Fetch document
    content, sec_url = fetch_prospectus_document(filing_url, doc_url)
    if not content:
        return {'saved': 0, 'errors': 1}

    # Extract offering details
    details = extract_offering_details(content, issuer_name, form_type)

    # Check for exclusion (10-K/10-Q updates, 8-K appendix, etc.)
    if details.get('skip_reason'):
        logger.info(f"Skipping {ticker} {form_type}: {details['skip_reason']}")
        return {'saved': 0, 'errors': 0, 'skipped': 1, 'skip_reason': details['skip_reason']}

    # Check for FWP deduplication: if this is a 424B5 priced offering,
    # check if a matching FWP already exists (FWP is more timely)
    if form_type in ('424B5', '424B2') and details.get('offering_type') == 'priced':
        matching_fwp = find_matching_priced_fwp(
            ticker=ticker,
            security_type=details.get('security_type', ''),
            principal_amount=details.get('principal_amount'),
            filing_date=message.get('filing_date', '')
        )
        if matching_fwp:
            logger.info(f"Skipping {ticker} {form_type}: superseded by FWP {matching_fwp.get('filing_url', '')[:50]}")
            return {'saved': 0, 'errors': 0, 'superseded': 1}

    # Save
    if save_prospectus(message, details, sec_url or filing_url):
        return {'saved': 1, 'errors': 0}
    return {'saved': 0, 'errors': 1}


def handler(event, context):
    """Lambda handler."""
    logger.info("Prospectus-Processor starting")

    stats = {'processed': 0, 'saved': 0, 'errors': 0, 'superseded': 0, 'skipped': 0}

    for record in event.get('Records', []):
        try:
            message = json.loads(record['body'])
            result = process_filing(message)
            stats['processed'] += 1
            stats['saved'] += result.get('saved', 0)
            stats['errors'] += result.get('errors', 0)
            stats['superseded'] += result.get('superseded', 0)
            stats['skipped'] += result.get('skipped', 0)
        except Exception as e:
            logger.error(f"Error: {e}")
            stats['errors'] += 1

    logger.info(f"Complete: {stats}")
    return {'statusCode': 200, 'body': json.dumps(stats)}
