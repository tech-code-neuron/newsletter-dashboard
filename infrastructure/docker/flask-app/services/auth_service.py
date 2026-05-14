"""
Authentication Service - OAuth Business Logic

SOLID Principles:
- Single Responsibility: Handles OAuth flow and user role management
- Dependency Inversion: Abstract from Cognito specifics
- Separation of Concerns: Routes delegate to this service

Responsibilities:
- Cognito configuration management
- OAuth token exchange
- User info fetching
- Role determination
- Redirect URI calculation
"""
import os
import json
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AuthService:
    """
    Service layer for authentication operations.

    Handles:
    - Cognito OAuth flow
    - User role management
    - Token exchange
    - Configuration management
    """

    def __init__(self):
        """Initialize service with AWS config."""
        from config.aws_config import aws_config
        self.aws_config = aws_config

    # =========================================================================
    # Configuration
    # =========================================================================

    def get_cognito_config(self) -> Dict[str, any]:
        """
        Get Cognito configuration from environment or Secrets Manager.

        Returns:
            dict: Cognito configuration (user_pool_id, client_id, etc.)
        """
        if self.aws_config.is_ecs:
            # Get from Secrets Manager
            config = self.aws_config.get_secret('reitsheet/cognito/config')
            if config:
                return config

        # Fallback to environment variables (local development)
        return {
            'user_pool_id': os.environ.get('COGNITO_USER_POOL_ID', ''),
            'client_id': os.environ.get('COGNITO_CLIENT_ID', ''),
            'client_secret': os.environ.get('COGNITO_CLIENT_SECRET', ''),
            'domain': os.environ.get('COGNITO_DOMAIN', ''),
            'region': os.environ.get('AWS_REGION', 'us-east-1'),
            'admin_emails': json.loads(os.environ.get('ADMIN_EMAILS', '[]')),
            'viewer_emails': json.loads(os.environ.get('VIEWER_EMAILS', '[]'))
        }

    def get_redirect_uri(self) -> str:
        """
        Get the OAuth redirect URI for AWS production environment.

        Returns:
            str: Redirect URI for OAuth callback (AWS only)
        """
        # AWS production only - use ALB DNS or custom domain
        base_url = os.environ.get('APP_BASE_URL', 'https://app.reitsheet.co')
        redirect_uri = f"{base_url}/auth/callback"
        logger.info(f"OAuth redirect URI: {redirect_uri}")
        return redirect_uri

    # =========================================================================
    # OAuth Token Exchange
    # =========================================================================

    def exchange_code_for_tokens(self, code: str) -> Optional[Dict]:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            dict: Tokens (access_token, id_token, refresh_token) or None on error
        """
        try:
            config = self.get_cognito_config()
            redirect_uri = self.get_redirect_uri()

            token_url = f"https://{config['domain']}/oauth2/token"

            data = {
                'grant_type': 'authorization_code',
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'code': code,
                'redirect_uri': redirect_uri
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(token_url, data=data, headers=headers, timeout=10)

            if response.status_code == 200:
                tokens = response.json()
                logger.info("Successfully exchanged code for tokens")
                return tokens
            else:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error exchanging code for tokens: {e}")
            return None

    def get_user_info(self, access_token: str) -> Optional[Dict]:
        """
        Fetch user info from Cognito userinfo endpoint.

        Args:
            access_token: Access token from OAuth flow

        Returns:
            dict: User info (email, name, etc.) or None on error
        """
        try:
            config = self.get_cognito_config()
            userinfo_url = f"https://{config['domain']}/oauth2/userInfo"

            headers = {
                'Authorization': f'Bearer {access_token}'
            }

            response = requests.get(userinfo_url, headers=headers, timeout=10)

            if response.status_code == 200:
                user_info = response.json()
                logger.info(f"Fetched user info for: {user_info.get('email', 'unknown')}")
                return user_info
            else:
                logger.error(f"User info fetch failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error fetching user info: {e}")
            return None

    # =========================================================================
    # User Role Management
    # =========================================================================

    def get_user_role(self, email: str) -> str:
        """
        Determine user role based on email whitelist.

        Args:
            email: User email address

        Returns:
            str: 'admin', 'viewer', or 'unauthorized'
        """
        config = self.get_cognito_config()
        admin_emails = config.get('admin_emails', [])
        viewer_emails = config.get('viewer_emails', [])

        email_lower = email.lower()

        if email_lower in [e.lower() for e in admin_emails]:
            return 'admin'
        elif email_lower in [e.lower() for e in viewer_emails]:
            return 'viewer'
        else:
            return 'unauthorized'

    def create_session_data(self, user_info: Dict, role: str) -> Dict:
        """
        Create session data for authenticated user.

        Args:
            user_info: User info from Cognito
            role: User role (admin/viewer)

        Returns:
            dict: Session data to store in Flask session
        """
        return {
            'email': user_info.get('email'),
            'name': user_info.get('name', user_info.get('email', 'User')),
            'role': role
        }

    # =========================================================================
    # Login URL Generation
    # =========================================================================

    def get_login_url(self) -> str:
        """
        Build Cognito login URL for OAuth redirect.

        Returns:
            str: Full Cognito login URL (goes directly to Google with account picker)

        Note (2026-03-15):
            - identity_provider=Google: Skips Cognito Hosted UI, goes directly to Google
            - prompt=select_account: Shows Google account picker (works with federated IdP)
            - Removed max_age=0 and prompt=login (don't work with federated IdP)
        """
        config = self.get_cognito_config()
        redirect_uri = self.get_redirect_uri()

        params = {
            'client_id': config['client_id'],
            'response_type': 'code',
            'scope': 'email openid profile',
            'redirect_uri': redirect_uri,
            'identity_provider': 'Google',   # Go directly to Google
            'prompt': 'select_account'        # Show Google account picker
        }

        from urllib.parse import urlencode
        login_url = f"https://{config['domain']}/oauth2/authorize?{urlencode(params)}"

        logger.info(f"Redirecting to Google OAuth via Cognito: {login_url}")
        return login_url

    def revoke_token(self, refresh_token: str) -> bool:
        """
        Revoke the refresh token to fully invalidate the session.

        This prevents auto-login after logout by invalidating the token
        at the Cognito level.

        Args:
            refresh_token: The refresh token to revoke

        Returns:
            bool: True if revocation succeeded, False otherwise
        """
        if not refresh_token:
            logger.warning("No refresh token to revoke")
            return False

        try:
            config = self.get_cognito_config()
            revoke_url = f"https://{config['domain']}/oauth2/revoke"

            data = {
                'token': refresh_token,
                'client_id': config['client_id']
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(revoke_url, data=data, headers=headers, timeout=10)

            if response.status_code == 200:
                logger.info("Successfully revoked refresh token")
                return True
            else:
                logger.error(f"Token revocation failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            return False

    def get_logout_url(self) -> str:
        """
        Build Cognito logout URL for session invalidation.

        Redirecting to this URL clears the Cognito/Google OAuth session,
        preventing auto-login after logout.

        Returns:
            str: Full Cognito logout URL
        """
        config = self.get_cognito_config()
        base_url = os.environ.get('APP_BASE_URL', 'https://app.reitsheet.co')
        logout_uri = f"{base_url}/logged-out"

        params = {
            'client_id': config['client_id'],
            'logout_uri': logout_uri
        }

        from urllib.parse import urlencode
        logout_url = f"https://{config['domain']}/logout?{urlencode(params)}"

        logger.info(f"Redirecting to Cognito logout: {logout_url}")
        return logout_url


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None

def get_auth_service() -> AuthService:
    """
    Get or create auth service instance (singleton).

    Returns:
        AuthService: Service instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = AuthService()
    return _service_instance
