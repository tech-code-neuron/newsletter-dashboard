"""
OG Image Endpoint
=================
Serves dynamically generated Open Graph images for press release permalinks.

Route: /og/release/<url_hash>.png
"""

import hashlib
import logging
from flask import Blueprint, Response, abort, redirect

from config.aws_config import aws_config

logger = logging.getLogger(__name__)

og_bp = Blueprint('og', __name__)

S3_BUCKET = 'reitsheet-social-cards'
CACHE_CONTROL = 'public, max-age=604800, immutable'


def compute_url_hash(url: str) -> str:
    """Compute SHA256 hash of URL, truncated to 16 chars."""
    return hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]


def get_release_by_hash(url_hash: str):
    """Look up a press release by its URL hash."""
    if not aws_config.is_ecs:
        return None

    table = aws_config.get_dynamodb_table(aws_config.reit_news_table_name)
    response = table.scan(
        FilterExpression='begins_with(url, :prefix)',
        ExpressionAttributeValues={':prefix': 'https://'},
        Limit=1000
    )

    for item in response.get('Items', []):
        if compute_url_hash(item.get('url', '')) == url_hash:
            return item

    return None


@og_bp.route('/og/release/<url_hash>.png')
def og_release_image(url_hash):
    """
    Generate or serve OG image for a press release.

    First request: generate card, upload to S3, serve bytes.
    Subsequent requests: redirect to S3 URL.
    """
    if len(url_hash) != 16:
        abort(404)

    if not aws_config.is_ecs:
        abort(503, description="OG images only available in production")

    release = get_release_by_hash(url_hash)
    if not release:
        abort(404)

    s3_key = f"og/{url_hash}.png"

    try:
        s3 = aws_config.s3.meta.client
        s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
        s3_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"
        return redirect(s3_url, code=302)
    except Exception:
        pass

    try:
        import sys
        import os
        shared_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambdas', 'shared')
        if shared_path not in sys.path:
            sys.path.insert(0, shared_path)

        from social.card_generator import generate_card

        png_bytes = generate_card(
            variant="x_summary_default",
            headline=release.get('display_title') or release.get('title', ''),
            category=release.get('classification_category', 'other'),
            ticker=release.get('ticker', ''),
            sector=release.get('sector', '')
        )

        s3 = aws_config.s3.meta.client
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=png_bytes,
            ContentType='image/png',
            CacheControl=CACHE_CONTROL
        )

        table = aws_config.get_dynamodb_table(aws_config.reit_news_table_name)
        table.update_item(
            Key={'url': release['url']},
            UpdateExpression='SET social_og_card_s3_key = :key',
            ExpressionAttributeValues={':key': s3_key}
        )

        return Response(
            png_bytes,
            mimetype='image/png',
            headers={'Cache-Control': CACHE_CONTROL}
        )

    except Exception as e:
        logger.error(f"Failed to generate OG image: {e}")
        abort(500, description="Failed to generate image")
