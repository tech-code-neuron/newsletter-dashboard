"""
Brave Review Blueprint - Low-Confidence Brave Search Results Review

Single Responsibility: Handles review of low-confidence Brave API search results

Routes:
- GET  /admin/brave-review           → Display review page with low-confidence results
- POST /admin/brave-review/approve   → Approve and move to press releases table
- POST /admin/brave-review/reject    → Reject and mark as dismissed
"""
import logging
from datetime import datetime, timezone

import boto3
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash

from config.aws_config import aws_config
from forms.brave_review_forms import BraveReviewActionForm
from routes.auth_decorators import login_required

logger = logging.getLogger(__name__)

# Create blueprint
brave_review_bp = Blueprint('brave_review', __name__)

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name=aws_config.aws_region)

# Table names
MANUAL_REVIEW_TABLE = 'reitsheet-manual-review'
REIT_NEWS_TABLE = 'reitsheet-reit-news-v2'
COMPANIES_TABLE = 'reitsheet-companies-config'


def get_brave_review_items(status='needs_review'):
    """Fetch low-confidence Brave search items from manual review table."""
    table = dynamodb.Table(MANUAL_REVIEW_TABLE)

    items = []
    scan_kwargs = {
        'FilterExpression': '#rt = :review_type AND #st = :status',
        'ExpressionAttributeNames': {
            '#rt': 'review_type',
            '#st': 'status'
        },
        'ExpressionAttributeValues': {
            ':review_type': 'brave_search_low_confidence',
            ':status': status
        }
    }

    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))

        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    # Sort by search_date descending, then by confidence score ascending
    items.sort(key=lambda x: (
        x.get('search_date', ''),
        -int(x.get('confidence_score', 0))
    ), reverse=True)

    return items


def get_company_name(ticker):
    """Get company name from ticker."""
    table = dynamodb.Table(COMPANIES_TABLE)
    try:
        response = table.scan(
            FilterExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': ticker},
            ProjectionExpression='company_name'
        )
        items = response.get('Items', [])
        if items:
            return items[0].get('company_name', ticker)
    except Exception as e:
        logger.error(f"Error fetching company name for {ticker}: {e}")
    return ticker


def approve_item(item_id):
    """Move item from manual review to press releases table."""
    review_table = dynamodb.Table(MANUAL_REVIEW_TABLE)
    news_table = dynamodb.Table(REIT_NEWS_TABLE)

    # Get the item
    response = review_table.get_item(Key={'id': item_id})
    item = response.get('Item')

    if not item:
        return False, "Item not found"

    now_iso = datetime.now(timezone.utc).isoformat()

    # Insert into press releases table
    try:
        news_table.put_item(Item={
            'url': item['url'],
            'ticker': item['ticker'],
            'title': item['title'],
            'press_release_date': item['search_date'],
            'source': 'brave_search',
            'first_seen_at': now_iso,
            'confidence_score': item.get('confidence_score', 0),
            'needs_scraping': False,
            'construction_method': 'brave_api_manual_approved'
        })

        # Update review item status
        review_table.update_item(
            Key={'id': item_id},
            UpdateExpression='SET #st = :status, approved_at = :approved_at',
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={
                ':status': 'approved',
                ':approved_at': now_iso
            }
        )

        return True, "Item approved and added to press releases"

    except Exception as e:
        logger.error(f"Error approving item {item_id}: {e}")
        return False, str(e)


def reject_item(item_id):
    """Mark item as rejected in manual review table."""
    review_table = dynamodb.Table(MANUAL_REVIEW_TABLE)
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        review_table.update_item(
            Key={'id': item_id},
            UpdateExpression='SET #st = :status, rejected_at = :rejected_at',
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={
                ':status': 'rejected',
                ':rejected_at': now_iso
            }
        )
        return True, "Item rejected"

    except Exception as e:
        logger.error(f"Error rejecting item {item_id}: {e}")
        return False, str(e)


@brave_review_bp.route('/admin/brave-review')
@login_required
def brave_review():
    """Display low-confidence Brave search results for review."""
    status_filter = request.args.get('status', 'needs_review')

    items = get_brave_review_items(status=status_filter)

    # Group by date
    items_by_date = {}
    for item in items:
        date = item.get('search_date', 'Unknown')
        if date not in items_by_date:
            items_by_date[date] = []
        items_by_date[date].append(item)

    # Get counts
    pending_count = len(get_brave_review_items(status='needs_review'))
    approved_count = len(get_brave_review_items(status='approved'))
    rejected_count = len(get_brave_review_items(status='rejected'))

    # Create form for CSRF protection
    form = BraveReviewActionForm()

    return render_template(
        'admin/brave_review.html',
        items=items,
        items_by_date=items_by_date,
        status_filter=status_filter,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        form=form
    )


@brave_review_bp.route('/admin/brave-review/approve', methods=['POST'])
@login_required
def approve():
    """Approve a low-confidence item and add to press releases."""
    form = BraveReviewActionForm()

    if not form.validate_on_submit():
        flash('Invalid form submission', 'error')
        return redirect(url_for('brave_review.brave_review'))

    item_id = form.item_id.data

    if not item_id:
        flash('Missing item ID', 'error')
        return redirect(url_for('brave_review.brave_review'))

    success, message = approve_item(item_id)

    if success:
        flash('Press release approved', 'success')
    else:
        flash(f'Error: {message}', 'error')

    return redirect(url_for('brave_review.brave_review'))


@brave_review_bp.route('/admin/brave-review/reject', methods=['POST'])
@login_required
def reject():
    """Reject a low-confidence item."""
    form = BraveReviewActionForm()

    if not form.validate_on_submit():
        flash('Invalid form submission', 'error')
        return redirect(url_for('brave_review.brave_review'))

    item_id = form.item_id.data

    if not item_id:
        flash('Missing item ID', 'error')
        return redirect(url_for('brave_review.brave_review'))

    success, message = reject_item(item_id)

    if success:
        flash('Item rejected', 'success')
    else:
        flash(f'Error: {message}', 'error')

    return redirect(url_for('brave_review.brave_review'))


@brave_review_bp.route('/api/brave-review/approve', methods=['POST'])
@login_required
def api_approve():
    """AJAX endpoint to approve an item."""
    data = request.get_json()
    item_id = data.get('item_id')

    if not item_id:
        return jsonify({'success': False, 'error': 'Missing item_id'}), 400

    success, message = approve_item(item_id)
    return jsonify({'success': success, 'message': message})


@brave_review_bp.route('/api/brave-review/reject', methods=['POST'])
@login_required
def api_reject():
    """AJAX endpoint to reject an item."""
    data = request.get_json()
    item_id = data.get('item_id')

    if not item_id:
        return jsonify({'success': False, 'error': 'Missing item_id'}), 400

    success, message = reject_item(item_id)
    return jsonify({'success': success, 'message': message})
