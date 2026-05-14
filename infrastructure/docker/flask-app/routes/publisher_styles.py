"""
Publisher Style Editor Routes

Endpoints for managing newsletter template styles.
Styles are persisted in DynamoDB for cross-session persistence.
"""
import json
import logging
import os
import boto3
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

bp = Blueprint('publisher_styles', __name__, url_prefix='/publisher/styles')

# DynamoDB table name (matches Terraform: reitsheet-app-settings)
APP_SETTINGS_TABLE = os.environ.get('APP_SETTINGS_TABLE', 'reitsheet-app-settings')
STYLES_KEY = 'newsletter_styles'

# Default styles (fallback if DynamoDB not available)
DEFAULT_STYLES = {
    'logo': {
        'fontFamily': 'Arial, sans-serif',
        'fontSize': '24px',
        'fontWeight': 'bold',
        'fontStyle': 'normal',
        'textDecoration': 'none',
        'color': '#0066cc',
        'letterSpacing': '1px',
        'textTransform': 'uppercase'
    },
    'date': {
        'fontFamily': 'Georgia, serif',
        'fontSize': '14px',
        'fontWeight': 'normal',
        'fontStyle': 'italic',
        'textDecoration': 'none',
        'color': '#666'
    },
    'company': {
        'fontFamily': 'Arial, sans-serif',
        'fontSize': '11px',
        'fontWeight': 'bold',
        'fontStyle': 'normal',
        'textDecoration': 'none',
        'color': '#0066cc',
        'textTransform': 'uppercase',
        'letterSpacing': '0.5px'
    },
    'title': {
        'fontFamily': 'Georgia, serif',
        'fontSize': '16px',
        'fontWeight': 'normal',
        'fontStyle': 'normal',
        'textDecoration': 'none',
        'color': '#333',
        'lineHeight': '1.45'
    },
    'source': {
        'fontFamily': 'Georgia, serif',
        'fontSize': '11px',
        'fontWeight': 'normal',
        'fontStyle': 'normal',
        'textDecoration': 'none',
        'color': '#999'
    },
    'footer': {
        'fontFamily': 'Georgia, serif',
        'fontSize': '12px',
        'fontWeight': 'normal',
        'fontStyle': 'normal',
        'textDecoration': 'none',
        'color': '#999'
    }
}


def _get_dynamodb_table():
    """Get DynamoDB table resource."""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    return dynamodb.Table(APP_SETTINGS_TABLE)


def get_styles_from_dynamodb():
    """
    Load styles from DynamoDB.

    Returns:
        dict: Style configuration, or DEFAULT_STYLES if not found
    """
    try:
        table = _get_dynamodb_table()
        response = table.get_item(Key={'setting_key': STYLES_KEY})

        if 'Item' in response and 'styles' in response['Item']:
            return response['Item']['styles']
        return DEFAULT_STYLES.copy()

    except ClientError as e:
        # Table doesn't exist or other error - return defaults
        logger.error(f"STYLES: DynamoDB error loading styles: {e}")
        return DEFAULT_STYLES.copy()
    except Exception as e:
        logger.error(f"STYLES: Error loading styles: {e}")
        return DEFAULT_STYLES.copy()


def save_styles_to_dynamodb(styles):
    """
    Save styles to DynamoDB.

    Args:
        styles: Style configuration dict

    Returns:
        tuple: (success: bool, error: str or None)
    """
    try:
        table = _get_dynamodb_table()
        table.put_item(Item={
            'setting_key': STYLES_KEY,
            'styles': styles,
            'updated_at': datetime.now(timezone.utc).isoformat()
        })
        return True, None

    except ClientError as e:
        error_msg = f"DynamoDB error: {e.response['Error']['Message']}"
        logger.error(f"STYLES: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = str(e)
        logger.error(f"STYLES: Error saving styles: {error_msg}")
        return False, error_msg


@bp.route('/', methods=['GET'])
def get_styles():
    """Get current style configuration."""
    logger.info("STYLES: GET /publisher/styles/")
    styles = get_styles_from_dynamodb()
    return jsonify(styles)


@bp.route('/', methods=['POST'])
def save_styles():
    """Save style configuration."""
    logger.info("STYLES: POST /publisher/styles/")
    try:
        styles = request.get_json()

        # Validate that all required elements are present
        required_elements = ['logo', 'date', 'company', 'title', 'source', 'footer']
        for element in required_elements:
            if element not in styles:
                return jsonify({'error': f'Missing element: {element}'}), 400

        # Save to DynamoDB
        success, error = save_styles_to_dynamodb(styles)

        if success:
            return jsonify({'success': True, 'message': 'Styles saved successfully'})
        else:
            return jsonify({'error': error or 'Failed to save styles'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
