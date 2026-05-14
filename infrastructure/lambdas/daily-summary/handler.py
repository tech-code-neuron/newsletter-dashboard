"""
Daily Email Summary Lambda - Send daily stats report to Outlook

Triggered by EventBridge at 6 PM daily
Queries DynamoDB email stats and sends formatted summary email
"""
import json
import boto3
import os
from datetime import datetime, timedelta

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================

_initialized = False
_config = {}
_tables = {}
_clients = {}


def _ensure_initialized():
    """Lazy initialization of AWS clients, env vars, and DynamoDB tables."""
    global _initialized, _config, _tables, _clients

    if _initialized:
        return

    _clients['dynamodb'] = boto3.resource('dynamodb')
    _clients['ses'] = boto3.client('ses')

    _config['EMAIL_STATS_TABLE'] = os.environ['EMAIL_STATS_TABLE']
    _config['SUMMARY_TO'] = os.environ['SUMMARY_TO']
    _config['SUMMARY_FROM'] = os.environ['SUMMARY_FROM']

    _tables['stats'] = _clients['dynamodb'].Table(_config['EMAIL_STATS_TABLE'])

    _initialized = True


def _stats_table():
    return _tables['stats']


def _ses():
    return _clients['ses']


def get_daily_stats(date_str):
    """
    Retrieve email statistics for a specific date from DynamoDB.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        dict: Statistics with counts for each category
    """
    try:
        response = _stats_table().get_item(Key={'date': date_str})

        if 'Item' not in response:
            return None

        item = response['Item']

        # Extract all statistics (handle missing attributes gracefully)
        # boto3.resource auto-deserializes, so values are native Python types
        def get_count(attr_name):
            return int(item.get(attr_name, 0))

        stats = {
            'date': date_str,
            'total': get_count('total_count'),
            'forwarded_company': get_count('forwarded_company_count'),
            'forwarded_8k': get_count('forwarded_8k_count'),
            'filtered': {
                '10-Q': get_count('filtered_10_q_count'),
                '10-K': get_count('filtered_10_k_count'),
                'Form 3': get_count('filtered_form_3_count'),
                'Form 4': get_count('filtered_form_4_count'),
                'Form 5': get_count('filtered_form_5_count'),
                'DEF 14A': get_count('filtered_def_14a_count'),
                'S-3': get_count('filtered_s_3_count'),
                'S-8': get_count('filtered_s_8_count'),
                'Other SEC': get_count('filtered_other_sec_count'),
                'Unknown': get_count('filtered_unknown_count'),
            },
            'spam': get_count('spam_count')
        }

        return stats

    except Exception as e:
        print(f"Error retrieving stats: {e}")
        return None


def format_summary_email(stats):
    """
    Format daily statistics into HTML email.

    Single Responsibility: Only formats HTML
    Open/Closed: Easy to add new sections

    Args:
        stats: Dictionary of statistics

    Returns:
        tuple: (subject, html_body, text_body)
    """
    date_formatted = datetime.strptime(stats['date'], '%Y-%m-%d').strftime('%B %d, %Y')

    forwarded_total = stats['forwarded_company'] + stats['forwarded_8k']
    filtered_total = sum(stats['filtered'].values())

    # Text version (for non-HTML clients)
    text_body = f"""REITsheet Daily Email Summary - {date_formatted}

Total Emails Received: {stats['total']}

FORWARDED TO OUTLOOK ({forwarded_total}):
  ✅ Company IR/PR Emails: {stats['forwarded_company']}
  ✅ SEC 8-K Filings: {stats['forwarded_8k']}

NOT FORWARDED - FILTERED ({filtered_total}):
  SEC Filings by Type:
"""

    # Add filtered filings (only non-zero counts)
    for filing_type, count in sorted(stats['filtered'].items()):
        if count > 0:
            text_body += f"  📄 {filing_type}: {count}\n"

    if filtered_total == 0:
        text_body += "  (No emails filtered today)\n"

    text_body += f"""
SPAM/REJECTED ({stats['spam']}):
"""
    if stats['spam'] == 0:
        text_body += "  ✅ No spam detected\n"
    else:
        text_body += f"  ⚠️ {stats['spam']} spam emails rejected\n"

    text_body += """
---
All emails stored in S3 and processed for newsletter
"""

    # HTML version (nicer formatting)
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .metric {{ background: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin: 10px 0; }}
        .metric-title {{ font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
        .count {{ font-size: 24px; font-weight: bold; color: #3498db; }}
        .category {{ padding: 8px 0; border-bottom: 1px solid #ecf0f1; }}
        .category:last-child {{ border-bottom: none; }}
        .emoji {{ font-size: 18px; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 2px solid #ecf0f1; color: #7f8c8d; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 REITsheet Daily Email Summary</h1>
        <p style="color: #7f8c8d;">{date_formatted}</p>

        <div class="metric">
            <div class="metric-title">Total Emails Received</div>
            <div class="count">{stats['total']}</div>
        </div>

        <div class="metric" style="border-left-color: #2ecc71;">
            <div class="metric-title">✅ FORWARDED TO OUTLOOK ({forwarded_total})</div>
            <div class="category">
                <span class="emoji">📧</span> Company IR/PR Emails: <strong>{stats['forwarded_company']}</strong>
            </div>
            <div class="category">
                <span class="emoji">📋</span> SEC 8-K Filings: <strong>{stats['forwarded_8k']}</strong>
            </div>
        </div>

        <div class="metric" style="border-left-color: #f39c12;">
            <div class="metric-title">🔕 NOT FORWARDED - FILTERED ({filtered_total})</div>
            <div style="margin-top: 8px; color: #7f8c8d; font-size: 14px;">SEC Filings by Type:</div>
"""

    # Add filtered filings (only non-zero counts)
    has_filtered = False
    for filing_type, count in sorted(stats['filtered'].items()):
        if count > 0:
            has_filtered = True
            html_body += f"""
            <div class="category">
                <span class="emoji">📄</span> {filing_type}: <strong>{count}</strong>
            </div>
"""

    if not has_filtered:
        html_body += """
            <div class="category" style="color: #7f8c8d; font-style: italic;">
                No emails filtered today
            </div>
"""

    html_body += """
        </div>
"""

    # Spam section
    spam_color = '#2ecc71' if stats['spam'] == 0 else '#e74c3c'
    spam_message = '✅ No spam detected' if stats['spam'] == 0 else f'⚠️ {stats["spam"]} spam emails rejected'

    html_body += f"""
        <div class="metric" style="border-left-color: {spam_color};">
            <div class="metric-title">SPAM/REJECTED ({stats['spam']})</div>
            <div class="category">
                {spam_message}
            </div>
        </div>

        <div class="footer">
            <p>All emails are stored in S3 and processed for the REITsheet newsletter.</p>
            <p>This is an automated daily summary sent at 6:00 PM EST.</p>
        </div>
    </div>
</body>
</html>
"""

    subject = f"📊 REITsheet Daily Summary - {date_formatted}"

    return subject, html_body, text_body


def lambda_handler(event, context):
    """
    Main Lambda handler - sends daily email summary.

    Triggered by EventBridge (CloudWatch Events) at 6 PM daily
    """
    # Lazy initialization (first invocation only)
    _ensure_initialized()

    try:
        # Get yesterday's stats (since summary runs at 6 PM, use yesterday's date)
        # For testing, use today's date
        today = datetime.utcnow().strftime('%Y-%m-%d')
        print(f"Generating summary for {today}")

        # Retrieve statistics from DynamoDB
        stats = get_daily_stats(today)

        if stats is None:
            print(f"No statistics found for {today} - skipping summary")
            return {
                'statusCode': 200,
                'body': json.dumps(f'No data for {today}')
            }

        # Skip if no emails received
        if stats['total'] == 0:
            print(f"No emails received on {today} - skipping summary")
            return {
                'statusCode': 200,
                'body': json.dumps('No emails received today')
            }

        print(f"Found {stats['total']} emails for {today}")

        # Format email
        subject, html_body, text_body = format_summary_email(stats)

        # Send via SES
        _ses().send_email(
            Source=_config['SUMMARY_FROM'],
            Destination={'ToAddresses': [_config['SUMMARY_TO']]},
            Message={
                'Subject': {'Data': subject},
                'Body': {
                    'Text': {'Data': text_body},
                    'Html': {'Data': html_body}
                }
            }
        )

        print(f"✅ Summary email sent to {_config['SUMMARY_TO']}")
        print(f"   Total: {stats['total']}, Forwarded: {stats['forwarded_company'] + stats['forwarded_8k']}, Filtered: {sum(stats['filtered'].values())}")

        return {
            'statusCode': 200,
            'body': json.dumps('Summary sent successfully')
        }

    except Exception as e:
        print(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
