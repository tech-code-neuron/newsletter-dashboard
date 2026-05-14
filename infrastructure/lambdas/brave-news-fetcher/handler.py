"""
Brave News Fetcher Lambda

Searches Brave API daily for private company press releases from PR newswires.
Results >= 75% confidence go to reitsheet-reit-news-v2.
Results < 75% confidence go to reitsheet-manual-review for human review.
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

import boto3
from brave_client import BraveSearchClient, calculate_confidence_score, JOURNALIST_PUBLICATION_DOMAINS
from metrics import emit_metric

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment variables
COMPANIES_TABLE = os.environ.get("COMPANIES_TABLE", "reitsheet-companies-config")
REIT_NEWS_TABLE = os.environ.get("REIT_NEWS_TABLE", "reitsheet-reit-news-v2")
MANUAL_REVIEW_TABLE = os.environ.get("MANUAL_REVIEW_TABLE", "reitsheet-manual-review")
CONFIDENCE_THRESHOLD = int(os.environ.get("CONFIDENCE_THRESHOLD", "75"))
SUMMARY_TO = os.environ.get("SUMMARY_TO", "your-email@your-domain.com")
SUMMARY_FROM = os.environ.get("SUMMARY_FROM", "alerts@your-domain.com")

# AWS clients
dynamodb = boto3.resource("dynamodb")
secrets_client = boto3.client("secretsmanager")
ses_client = boto3.client("ses")

# Social media pipeline imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
try:
    from sector_utils import get_sector_for_ticker
    from slug_utils import generate_release_slug
    from social_constants import SOCIAL_STATUS_BODY_NEEDED
except ImportError:
    def get_sector_for_ticker(ticker): return None
    def generate_release_slug(title): return None
    SOCIAL_STATUS_BODY_NEEDED = 'body_needed'

# Exact paths to reject for publications (shallow/section pages)
REJECT_EXACT_PATHS = {
    # Bloomberg
    "/", "/europe", "/canada", "/asia", "/uk", "/australia",
    "/middle-east", "/africa", "/businessweek", "/technology",
    "/politics", "/opinion", "/markets", "/markets/stocks",
    "/markets/rates", "/markets/currencies",
    "/markets/stocks/world-indexes/americas",
    # WSJ
    "/buyside",
}

# Path prefixes to reject (media, live coverage)
REJECT_PATH_PREFIXES = [
    "/news/audio/", "/news/video/", "/livecoverage/", "/section/",
]

# Junk title phrases to reject (financial bulletins, not press releases)
# Add new phrases here as you encounter them
JUNK_TITLE_PHRASES = {
    "treasury bond auction",
    "switch auction",
    "cash payment",
    "bond auction announcement",
}


def is_junk_title(title: str) -> bool:
    """Reject titles with junk phrases or financial code patterns."""
    title_lower = title.lower()

    # Check phrase blocklist
    if any(phrase in title_lower for phrase in JUNK_TITLE_PHRASES):
        return True

    # Financial code pattern: "RIKB 27 0415" (2-5 uppercase + space + digits)
    if re.search(r'\b[A-Z]{2,5}\s+\d{2}\s+\d{4}\b', title):
        return True

    # Excessive dashes: "X - Y - Z - W" (code-like structure)
    if title.count(' - ') >= 3:
        return True

    return False


def is_publication_article(url: str) -> bool:
    """Check if URL looks like an article based on nesting and hyphens."""
    url_lower = url.lower()
    path = url_lower.split("?")[0]  # Remove query params

    # Extract path after domain
    if "://" in path:
        path = "/" + "/".join(path.split("://")[1].split("/")[1:])
    path = path.rstrip("/") or "/"

    # Reject exact shallow/section paths
    if path in REJECT_EXACT_PATHS:
        return False

    # Reject media/live coverage prefixes
    if any(path.startswith(prefix) for prefix in REJECT_PATH_PREFIXES):
        return False

    # FT.com: require /content/ with UUID
    if "ft.com" in url_lower:
        return bool(re.search(r"/content/[a-f0-9-]{36}", path))

    # NYT: require date pattern /YYYY/MM/DD/ in path
    if "nytimes.com" in url_lower:
        return bool(re.search(r"/20\d{2}/\d{2}/\d{2}/", path))

    # Bisnow: require /category/slug-with-id pattern
    if "bisnow.com" in url_lower:
        return bool(re.search(r"/[a-z-]+/[a-z0-9-]+-\d+$", path))

    # For Bloomberg, WSJ: require nesting + hyphens
    segments = [s for s in path.split("/") if s]
    hyphen_count = path.count("-")

    # Require: 3+ path segments AND 2+ hyphens
    return len(segments) >= 3 and hyphen_count >= 2


def url_exists(url: str) -> bool:
    """Check if URL already exists in press releases table (de-dupe)."""
    table = dynamodb.Table(REIT_NEWS_TABLE)
    response = table.get_item(
        Key={'url': url},
        ProjectionExpression='#u',
        ExpressionAttributeNames={'#u': 'url'}
    )
    return 'Item' in response


def get_api_key() -> str:
    """Fetch Brave API key from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId="reitsheet/brave-search-api-key")
    return response["SecretString"]


def get_private_companies() -> list:
    """Fetch all active private companies from DynamoDB."""
    table = dynamodb.Table(COMPANIES_TABLE)
    companies = []

    scan_kwargs = {
        "FilterExpression": "is_public = :false AND active = :true",
        "ExpressionAttributeValues": {":false": False, ":true": True},
        "ProjectionExpression": "company_name, ticker, sector"
    }

    while True:
        response = table.scan(**scan_kwargs)
        companies.extend(response.get("Items", []))

        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    # Filter out entries without a name, using company_name or name field
    result = []
    for c in companies:
        name = c.get("company_name") or c.get("name")
        if name:
            c["company_name"] = name  # Normalize to company_name
            result.append(c)
    return result


def get_today_date_et() -> str:
    """Get today's date in ET timezone as YYYY-MM-DD."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    return datetime.now(et).strftime("%Y-%m-%d")


def get_search_date_range(end_date: str) -> tuple[str, str]:
    """
    Calculate search date range based on day of week.

    - Monday: search Friday to Monday (4 days) to catch weekend articles
    - Other days: search yesterday to today (2 days)

    Args:
        end_date: End date in YYYY-MM-DD format

    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    from datetime import timedelta

    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    weekday = end_dt.weekday()  # Monday = 0, Sunday = 6

    if weekday == 0:  # Monday - search back to Friday
        days_back = 3
    else:  # Other days - search yesterday and today
        days_back = 1

    start_dt = end_dt - timedelta(days=days_back)
    return start_dt.strftime("%Y-%m-%d"), end_date


def save_press_release(url: str, ticker: str, title: str, date: str, confidence: int):
    """Save high-confidence result to press releases table."""
    table = dynamodb.Table(REIT_NEWS_TABLE)
    now_iso = datetime.now(timezone.utc).isoformat()

    item = {
        "url": url,
        "ticker": ticker,
        "title": title,
        "press_release_date": date,
        "source": "brave_search",
        "first_seen_at": now_iso,
        "confidence_score": confidence,
        "needs_scraping": False,
        "construction_method": "brave_api",
        # Social media pipeline fields
        "sector": get_sector_for_ticker(ticker),
        "release_slug": generate_release_slug(title),
        "social_status": SOCIAL_STATUS_BODY_NEEDED  # Brave API returns title only
    }

    table.put_item(Item=item)
    logger.info(json.dumps({
        "event": "press_release_saved",
        "url": url,
        "ticker": ticker,
        "confidence": confidence
    }))


def save_for_review(company_name: str, ticker: str, url: str, title: str,
                    date: str, confidence: int):
    """Save low-confidence result to manual review table."""
    table = dynamodb.Table(MANUAL_REVIEW_TABLE)
    now_iso = datetime.now(timezone.utc).isoformat()

    item = {
        "id": str(uuid.uuid4()),
        "status": "needs_review",
        "review_type": "brave_search_low_confidence",
        "company_name": company_name,
        "ticker": ticker,
        "url": url,
        "title": title,
        "confidence_score": confidence,
        "search_date": date,
        "saved_for_review_at": now_iso
    }

    table.put_item(Item=item)
    logger.info(json.dumps({
        "event": "saved_for_review",
        "url": url,
        "company": company_name,
        "confidence": confidence
    }))


def process_company(client: BraveSearchClient, company: dict, start_date: str,
                    end_date: str) -> dict:
    """Search for a single company and process results.

    Args:
        client: BraveSearchClient instance
        company: Company dict with company_name and ticker
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    company_name = company["company_name"]
    ticker = company["ticker"]

    start_time = time.time()

    try:
        results = client.search_all_sources(company_name, start_date, end_date)
        duration_ms = int((time.time() - start_time) * 1000)

        high_confidence = 0
        low_confidence = 0
        high_confidence_urls = []
        low_confidence_urls = []

        for result in results:
            url = result.get("url", "")
            title = result.get("title", "")
            description = result.get("description", "")

            # Determine source type from URL domain
            domain = url.split('/')[2].lower() if url.startswith('http') else ''
            is_publication = domain in JOURNALIST_PUBLICATION_DOMAINS
            source_type = "publications" if is_publication else "newswires"

            # Pre-filter: skip results where company name is not in title
            # This eliminates homepage/section pages that don't mention the company
            title_lower = title.lower()
            company_lower = company_name.lower()
            # Get significant words (>3 chars) from company name
            significant_words = [w for w in company_lower.split() if len(w) > 3]
            if significant_words and not any(w in title_lower for w in significant_words):
                logger.info(json.dumps({
                    "event": "result_filtered_no_company_in_title",
                    "company": company_name,
                    "title": title[:100],
                    "url": url
                }))
                continue

            # Skip junk press releases (financial bulletins, treasury announcements)
            if is_junk_title(title):
                logger.info(f"Skipping junk title: {title[:80]}")
                continue

            # For publications: filter by URL pattern (must look like an article)
            if is_publication and not is_publication_article(url):
                continue  # Skip non-article pages (homepages, sections, etc.)

            confidence = calculate_confidence_score(
                company_name, title, url, description
            )

            # De-dupe: skip if URL already exists in database
            if url_exists(url):
                logger.info(json.dumps({"event": "url_already_exists", "url": url, "ticker": ticker}))
                continue

            # Auto-add if meets threshold (both newswires and publications)
            if confidence >= CONFIDENCE_THRESHOLD:
                save_press_release(url, ticker, title, end_date, confidence)
                high_confidence += 1
                high_confidence_urls.append({
                    "company": company_name,
                    "url": url,
                    "confidence": confidence,
                    "source": source_type
                })
            else:
                save_for_review(company_name, ticker, url, title, end_date, confidence)
                low_confidence += 1
                low_confidence_urls.append({
                    "company": company_name,
                    "url": url,
                    "confidence": confidence,
                    "source": source_type
                })

        logger.info(json.dumps({
            "event": "company_search",
            "company": company_name,
            "ticker": ticker,
            "source_type": "all",
            "results_found": len(results),
            "high_confidence": high_confidence,
            "low_confidence": low_confidence,
            "duration_ms": duration_ms
        }))

        return {
            "company": company_name,
            "results": len(results),
            "ingested": high_confidence,
            "review": low_confidence,
            "high_confidence_urls": high_confidence_urls,
            "low_confidence_urls": low_confidence_urls,
            "error": None
        }

    except Exception as e:
        logger.error(json.dumps({
            "event": "company_search_error",
            "company": company_name,
            "error": str(e)
        }))
        emit_metric("BraveSearchAPIErrors", 1)
        return {
            "company": company_name,
            "results": 0,
            "ingested": 0,
            "review": 0,
            "high_confidence_urls": [],
            "low_confidence_urls": [],
            "error": str(e)
        }


def send_summary_email(search_date: str, high_confidence_urls: list,
                       low_confidence_urls: list, total_companies: int,
                       total_errors: int):
    """Send email summary of Brave search results."""
    from datetime import datetime

    # Handle date range (e.g., "2026-04-06 to 2026-04-07") or single date
    if " to " in search_date:
        start_str, end_str = search_date.split(" to ")
        start_fmt = datetime.strptime(start_str, "%Y-%m-%d").strftime("%B %d")
        end_fmt = datetime.strptime(end_str, "%Y-%m-%d").strftime("%B %d, %Y")
        date_formatted = f"{start_fmt} - {end_fmt}"
    else:
        date_formatted = datetime.strptime(search_date, "%Y-%m-%d").strftime("%B %d, %Y")

    # Build text body
    text_lines = [
        f"Brave Search Results - {date_formatted}",
        f"Companies searched: {total_companies}",
        f"Errors: {total_errors}",
        "",
        f"=== ADDED TO DATABASE ({len(high_confidence_urls)}) ===",
    ]

    if high_confidence_urls:
        for item in high_confidence_urls:
            text_lines.append(f"  {item['company']} ({item['confidence']}%): {item['url']}")
    else:
        text_lines.append("  (none)")

    text_lines.extend([
        "",
        f"=== NEEDS MANUAL REVIEW ({len(low_confidence_urls)}) ===",
    ])

    if low_confidence_urls:
        for item in low_confidence_urls:
            text_lines.append(f"  {item['company']} ({item['confidence']}%): {item['url']}")
    else:
        text_lines.append("  (none)")

    text_body = "\n".join(text_lines)

    # Build HTML body
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }}
        .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .section {{ background: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; }}
        .section-title {{ font-weight: bold; color: #2c3e50; margin-bottom: 10px; font-size: 16px; }}
        .section.high {{ border-left-color: #2ecc71; }}
        .section.low {{ border-left-color: #f39c12; }}
        .item {{ padding: 8px 0; border-bottom: 1px solid #ecf0f1; }}
        .item:last-child {{ border-bottom: none; }}
        .company {{ font-weight: bold; color: #2c3e50; }}
        .confidence {{ color: #7f8c8d; font-size: 12px; }}
        .url {{ color: #3498db; word-break: break-all; font-size: 13px; }}
        .stats {{ color: #7f8c8d; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Brave Search Results</h1>
        <p class="stats">{date_formatted} | Companies: {total_companies} | Errors: {total_errors}</p>

        <div class="section high">
            <div class="section-title">ADDED TO DATABASE ({len(high_confidence_urls)})</div>
"""

    if high_confidence_urls:
        for item in high_confidence_urls:
            html_body += f"""
            <div class="item">
                <span class="company">{item['company']}</span>
                <span class="confidence">({item['confidence']}%)</span><br>
                <a class="url" href="{item['url']}">{item['url']}</a>
            </div>
"""
    else:
        html_body += '<div class="item" style="color: #7f8c8d;">No results</div>'

    html_body += """
        </div>

        <div class="section low">
            <div class="section-title">NEEDS MANUAL REVIEW ({len_low})</div>
""".replace("{len_low}", str(len(low_confidence_urls)))

    if low_confidence_urls:
        for item in low_confidence_urls:
            html_body += f"""
            <div class="item">
                <span class="company">{item['company']}</span>
                <span class="confidence">({item['confidence']}%)</span><br>
                <a class="url" href="{item['url']}">{item['url']}</a>
            </div>
"""
    else:
        html_body += '<div class="item" style="color: #7f8c8d;">No results</div>'

    html_body += """
        </div>
    </div>
</body>
</html>
"""

    subject = f"Brave Search: {len(high_confidence_urls)} added, {len(low_confidence_urls)} for review - {date_formatted}"

    try:
        ses_client.send_email(
            Source=SUMMARY_FROM,
            Destination={"ToAddresses": [SUMMARY_TO]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": text_body},
                    "Html": {"Data": html_body}
                }
            }
        )
        logger.info(json.dumps({
            "event": "summary_email_sent",
            "to": SUMMARY_TO,
            "high_confidence_count": len(high_confidence_urls),
            "low_confidence_count": len(low_confidence_urls)
        }))
    except Exception as e:
        logger.error(json.dumps({
            "event": "summary_email_failed",
            "error": str(e)
        }))


def lambda_handler(event, context):
    """Main Lambda handler."""
    start_time = time.time()

    logger.info(json.dumps({"event": "handler_start", "input": event}))

    # Get API key and initialize client
    api_key = get_api_key()
    client = BraveSearchClient(api_key)

    # Get private companies
    companies = get_private_companies()
    logger.info(json.dumps({
        "event": "companies_loaded",
        "count": len(companies)
    }))

    # Get search date range (today and yesterday, or Friday-Monday on Mondays)
    end_date = event.get("search_date") or get_today_date_et()
    start_date, end_date = get_search_date_range(end_date)

    logger.info(json.dumps({
        "event": "date_range_calculated",
        "start_date": start_date,
        "end_date": end_date
    }))

    # Optional limit for testing (to reduce API costs)
    limit = event.get("limit")
    if limit:
        companies = companies[:limit]
        logger.info(json.dumps({
            "event": "companies_limited",
            "limit": limit,
            "processing": len(companies)
        }))

    # Process each company against all sources (8 sites)
    results = []
    total_ingested = 0
    total_review = 0
    total_errors = 0
    all_high_confidence = []
    all_low_confidence = []

    for i, company in enumerate(companies):
        result = process_company(client, company, start_date, end_date)
        results.append(result)

        total_ingested += result["ingested"]
        total_review += result["review"]
        all_high_confidence.extend(result["high_confidence_urls"])
        all_low_confidence.extend(result["low_confidence_urls"])
        if result["error"]:
            total_errors += 1

        # Rate limit: Brave allows 1 req/sec, using 0.5s for faster processing
        if i < len(companies) - 1:
            time.sleep(0.5)

    duration_ms = int((time.time() - start_time) * 1000)

    # Emit metrics
    emit_metric("BraveSearchCompaniesProcessed", len(companies))
    emit_metric("BraveSearchResultsIngested", total_ingested)
    emit_metric("BraveSearchLowConfidence", total_review)
    emit_metric("BraveSearchDuration", duration_ms)

    # Send email summary
    date_range_str = f"{start_date} to {end_date}" if start_date != end_date else end_date
    send_summary_email(
        search_date=date_range_str,
        high_confidence_urls=all_high_confidence,
        low_confidence_urls=all_low_confidence,
        total_companies=len(companies),
        total_errors=total_errors
    )

    summary = {
        "event": "handler_complete",
        "start_date": start_date,
        "end_date": end_date,
        "companies_processed": len(companies),
        "total_ingested": total_ingested,
        "total_for_review": total_review,
        "total_errors": total_errors,
        "duration_ms": duration_ms
    }

    logger.info(json.dumps(summary))

    return {
        "statusCode": 200,
        "body": json.dumps(summary)
    }
