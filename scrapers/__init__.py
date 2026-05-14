"""
Platform-specific scrapers package.
"""
from scrapers.welltower import WelltowerScraper
from scrapers.apollo_accordion import ApolloAccordionScraper
from scrapers.q4_pdf import Q4PdfScraper
from scrapers.q4_detail import Q4DetailScraper
from scrapers.q4_drupal_html import Q4DrupalHtmlScraper
from scrapers.q4_drupal_js import Q4DrupalJsScraper
from scrapers.investis import InvestisScraper
from scrapers.wordpress_pdf import WordpressPdfScraper
from scrapers.date_slug import DateSlugScraper
from scrapers.olp_pdf import OlpPdfScraper
from scrapers.gcs import GcsScraper
from scrapers.gcs_with_dates import GcsWithDatesScraper

__all__ = [
    'WelltowerScraper',
    'ApolloAccordionScraper',
    'Q4PdfScraper',
    'Q4DetailScraper',
    'Q4DrupalHtmlScraper',
    'Q4DrupalJsScraper',
    'InvestisScraper',
    'WordpressPdfScraper',
    'DateSlugScraper',
    'OlpPdfScraper',
    'GcsScraper',
    'GcsWithDatesScraper'
]
