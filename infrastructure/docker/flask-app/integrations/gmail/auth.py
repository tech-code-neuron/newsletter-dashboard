"""
Gmail API Authentication Module

Single source of truth for Gmail authentication.
Reusable across all files that need Gmail access.
"""
import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from utils.review_constants import GMAIL_SCOPES, GMAIL_TOKEN_FILE, GMAIL_CREDENTIALS_FILE


def authenticate_gmail():
    """
    Authenticate with Gmail API and return service object.

    Handles token caching, refresh, and initial OAuth flow.

    Returns:
        googleapiclient.discovery.Resource: Gmail API service object

    Raises:
        FileNotFoundError: If credentials file is missing
        Exception: If authentication fails
    """
    creds = None

    # Load cached token if exists
    if os.path.exists(GMAIL_TOKEN_FILE):
        with open(GMAIL_TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            creds.refresh(Request())
        else:
            # Run OAuth flow
            if not os.path.exists(GMAIL_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {GMAIL_CREDENTIALS_FILE}\n"
                    "Download from Google Cloud Console and save as gmail-credentials.json"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE,
                GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next time
        with open(GMAIL_TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    # Build and return Gmail service
    return build('gmail', 'v1', credentials=creds)


def get_message_header(message, header_name):
    """
    Extract header value from Gmail message.

    Args:
        message (dict): Gmail API message object (format='full')
        header_name (str): Header name (case-insensitive)

    Returns:
        str: Header value, or empty string if not found
    """
    for header in message['payload']['headers']:
        if header['name'].lower() == header_name.lower():
            return header['value']
    return ''
