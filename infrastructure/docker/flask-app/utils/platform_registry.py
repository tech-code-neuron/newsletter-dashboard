"""
Platform detection and routing registry
Implements Strategy Pattern for platform-specific scrapers (Open/Closed Principle)
"""
import logging

logger = logging.getLogger(__name__)


class PlatformRegistry:
    """
    Registry for platform detection and routing.
    Separates platform detection logic from scraper implementation (Single Responsibility).
    """

    @staticmethod
    def get_platform_router(scraper_instance):
        """
        Returns a mapping of platform names to their scraper methods.
        This implements the Strategy Pattern - new platforms can be added
        without modifying routing logic (Open/Closed Principle).

        Args:
            scraper_instance: Instance of PressReleaseScraper with scraper methods

        Returns:
            dict: {platform_name: scraper_method}
        """
        return {
            'gcs': scraper_instance.scrape_gcs,
            'gcs_with_dates': scraper_instance.scrape_gcs_with_dates,
            'investis': scraper_instance.scrape_investis,
            'apollo_accordion': scraper_instance.scrape_apollo_accordion,
            'date_slug': scraper_instance.scrape_date_slug,
            'welltower': scraper_instance.scrape_welltower,
            'olp_pdf': scraper_instance.scrape_olp_pdf,
            'wordpress_pdf': scraper_instance.scrape_wordpress_pdf,
            'q4_detail': scraper_instance.scrape_q4_detail,
            'q4_pdf': scraper_instance.scrape_q4_pdf,
            'q4_js': scraper_instance.scrape_js_q4_drupal,
            'q4_drupal': scraper_instance.scrape_html_q4_drupal,
        }

    @staticmethod
    def route_to_scraper(scraper_instance, company, lookback_days):
        """
        Routes a company to the appropriate scraper method based on its platform.
        This centralizes routing logic (Single Responsibility Principle).

        Args:
            scraper_instance: Instance of PressReleaseScraper
            company: Company model instance
            lookback_days: How far back to scrape

        Returns:
            tuple: (new_count, platform_key) where platform_key is for results tracking
        """
        router = PlatformRegistry.get_platform_router(scraper_instance)

        # Check GCS variants first (by scraper_variant or URL)
        if company.scraper_variant == 'gcs_with_dates':
            return router['gcs_with_dates'](company, lookback_days), 'gcs'
        elif company.scraper_variant == 'gcs' or (company.ir_url and 'gcs-web.com' in company.ir_url):
            return router['gcs'](company, lookback_days), 'gcs'

        # Route by ir_platform
        platform = company.ir_platform
        if platform and platform in router:
            return router[platform](company, lookback_days), platform

        # Fallback to legacy HTML scraper
        return scraper_instance.scrape_company(company, lookback_days), 'html_fallback'

    # ═══════════════════════════════════════════════════════════
    # PLATFORM DETECTION - Chain of Responsibility Pattern
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def detect_gcs_platform(html, press_url, ticker):
        """Detect GCS platform variant"""
        if 'gcs-web.com' in press_url or 'gcs-web.com' in html:
            if '/news-release-details/' in html or '/news-releases/news-release-details/' in html:
                logger.info(f"[{ticker}] Detected: gcs_with_dates")
                return 'gcs_with_dates'
            elif '/static-files/' in html:
                logger.info(f"[{ticker}] Detected: custom (standard GCS)")
                return 'custom'
        return None

    @staticmethod
    def detect_q4_platform(html, ticker):
        """Detect Q4 platform variant"""
        if 'q4inc.com' in html or 'q4web.com' in html or 'q4cdn.com' in html:
            if '/press-releases/detail/' in html:
                logger.info(f"[{ticker}] Detected: q4_detail")
                return 'q4_detail'
            elif 'press-releases-details' in html or '-details/' in html:
                logger.info(f"[{ticker}] Detected: q4_js (may need Playwright)")
                return 'q4_js'
            elif 'news-release-details' in html:
                logger.info(f"[{ticker}] Detected: q4_drupal")
                return 'q4_drupal'
            else:
                logger.info(f"[{ticker}] Detected: q4_js (generic Q4)")
                return 'q4_js'
        return None

    @staticmethod
    def detect_wordpress_platform(html, ticker):
        """Detect WordPress platform variant"""
        if 'wp-content' in html or 'wordpress' in html.lower():
            if '.pdf' in html and '/press-release' in html:
                logger.info(f"[{ticker}] Detected: wordpress_pdf")
                return 'wordpress_pdf'
            else:
                logger.info(f"[{ticker}] Detected: WordPress HTML (needs custom scraper)")
                return None
        return None

    @staticmethod
    def detect_investis_platform(html, ticker):
        """Detect Investis platform"""
        if 'investis' in html.lower():
            logger.info(f"[{ticker}] Detected: Investis (needs custom scraper)")
            return None
        return None

    @staticmethod
    def detect_platform(scraper_instance, company):
        """
        Auto-detect the correct scraper platform for a company by testing patterns.
        Uses Chain of Responsibility pattern - each detector runs in sequence.

        This function:
        1. Fetches the company's IR page HTML
        2. Checks for known platform indicators using detector methods
        3. Returns the detected platform string or None

        Does NOT modify the database - caller should save the result.

        Args:
            scraper_instance: Instance of PressReleaseScraper (for session access)
            company: Company model instance

        Returns:
            str: Platform identifier ('q4_detail', 'q4_js', 'gcs_with_dates', etc.) or None
        """
        from config.scraper_config import TIMEOUT_MEDIUM

        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL to detect platform")
            return None

        logger.info(f"[{company.ticker}] Detecting platform from {press_url}")

        try:
            # Fetch the page
            response = scraper_instance.session.get(press_url, timeout=TIMEOUT_MEDIUM)
            html = response.text

            # Chain of Responsibility - try each detector in order
            detectors = [
                lambda: PlatformRegistry.detect_gcs_platform(html, press_url, company.ticker),
                lambda: PlatformRegistry.detect_q4_platform(html, company.ticker),
                lambda: PlatformRegistry.detect_wordpress_platform(html, company.ticker),
                lambda: PlatformRegistry.detect_investis_platform(html, company.ticker),
            ]

            for detector in detectors:
                result = detector()
                if result is not None:
                    return result

            # Couldn't detect - return None
            logger.warning(f"[{company.ticker}] Could not auto-detect platform")
            return None

        except Exception as e:
            logger.error(f"[{company.ticker}] Platform detection failed: {e}")
            return None
