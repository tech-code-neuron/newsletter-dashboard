"""
Blueprint for action routes (background operations)

Handles POST-only routes for:
- Scraping all companies (local only - requires SQLite)
- Categorizing press releases (local only - requires SQLite)
- Newsletter generation and regeneration (local only - requires SQLite)
- Press release soft delete/restore operations (works in ECS)

Uses Repository Pattern for database abstraction (DynamoDB in ECS, SQLite local).

ECS Support:
- Bulk delete/restore operations work in both ECS and local
- Scraping, categorization, and newsletter generation are local-only
  (these imports are deferred to avoid boot failures in ECS)
"""
from flask import Blueprint, request, redirect, url_for, flash

from core.repositories import get_press_release_repo, get_newsletter_repo
from config.aws_config import aws_config
from utils.datetime_utils import calculate_newsletter_date_range
import pytz

# Blueprint configuration
actions_bp = Blueprint('actions', __name__, url_prefix='/actions')

# Constants
DEFAULT_SCRAPE_LOOKBACK_DAYS = 14


# ------------------------------------------------------------------
# SCRAPING AND CATEGORIZATION ACTIONS (Local Only)
# ------------------------------------------------------------------

@actions_bp.route('/scrape', methods=['POST'])
def action_scrape():
    """Scrape all companies for new press releases (local only)"""
    if aws_config.is_ecs:
        flash('Scraping is not available in ECS - handled by Lambda pipeline', 'info')
        return redirect(url_for('dashboard.index'))

    try:
        from core.scraper import PressReleaseScraper
        scraper = PressReleaseScraper()
        new_count = scraper.scrape_all_companies(lookback_days=DEFAULT_SCRAPE_LOOKBACK_DAYS, rss_only=True)
        scraper.close()
        flash(f'Scraping complete! Found {new_count} new press releases.', 'success')
    except Exception as e:
        flash(f'Scraping failed: {str(e)}', 'error')
    return redirect(url_for('dashboard.index'))


@actions_bp.route('/categorize', methods=['POST'])
def action_categorize():
    """Categorize uncategorized press releases (local only)"""
    if aws_config.is_ecs:
        flash('Categorization is not available in ECS', 'info')
        return redirect(url_for('dashboard.index'))

    try:
        from core.categorizer import PressReleaseCategorizer
        categorizer = PressReleaseCategorizer()
        count = categorizer.categorize_uncategorized()
        categorizer.close()
        flash(f'Categorization complete! Processed {count} press releases.', 'success')
    except Exception as e:
        flash(f'Categorization failed: {str(e)}', 'error')
    return redirect(url_for('dashboard.index'))


# ------------------------------------------------------------------
# NEWSLETTER GENERATION ACTIONS (Local Only)
# ------------------------------------------------------------------

@actions_bp.route('/generate-newsletter', methods=['POST'])
def action_generate_newsletter():
    """Generate new morning and breaking newsletters (local only)"""
    if aws_config.is_ecs:
        flash('Newsletter generation is not available in ECS', 'info')
        return redirect(url_for('newsletters.newsletters'))

    try:
        from core.newsletter_generator import NewsletterGenerator
        generator = NewsletterGenerator()
        morning = generator.create_newsletter('morning')
        breaking = generator.create_newsletter('breaking')
        generator.save_newsletter_to_file(morning)
        generator.save_newsletter_to_file(breaking)
        generator.close()
        flash(f'Newsletters generated! Morning: ID {morning.id}, Breaking: ID {breaking.id}', 'success')
    except Exception as e:
        flash(f'Newsletter generation failed: {str(e)}', 'error')
    return redirect(url_for('newsletters.newsletters'))


@actions_bp.route('/regenerate-newsletter/<newsletter_id>', methods=['POST'])
def action_regenerate_newsletter(newsletter_id):
    """Regenerate an existing newsletter with current data (local only)"""
    if aws_config.is_ecs:
        flash('Newsletter regeneration is not available in ECS', 'info')
        return redirect(url_for('newsletters.newsletters'))

    try:
        from core.newsletter_generator import NewsletterGenerator
        newsletter_repo = get_newsletter_repo()
        newsletter = newsletter_repo.get_by_id(newsletter_id)

        if not newsletter:
            flash('Newsletter not found', 'error')
            return redirect(url_for('newsletters.newsletters'))

        generator = NewsletterGenerator()
        et_tz = pytz.timezone('US/Eastern')

        if newsletter.date:
            date = et_tz.localize(newsletter.date) if newsletter.date.tzinfo is None else newsletter.date
        else:
            from datetime import datetime
            date = et_tz.localize(datetime.now())

        # Use helper function to calculate date range
        start_date_utc, end_date_utc = calculate_newsletter_date_range(newsletter.newsletter_type, date)

        press_releases = generator.get_press_releases_for_period(
            start_date_utc,
            end_date_utc,
            breaking_only=(newsletter.newsletter_type == 'breaking')
        )

        new_html = generator.generate_html(newsletter.newsletter_type, press_releases, date)

        # Update newsletter
        newsletter_repo.update(newsletter_id, {'html_content': new_html})

        # Save to file (needs newsletter object with updated content)
        newsletter.html_content = new_html
        generator.save_newsletter_to_file(newsletter)
        generator.close()

        flash('Newsletter regenerated successfully!', 'success')
        return redirect(url_for('newsletters.edit_newsletter', newsletter_id=newsletter_id))

    except Exception as e:
        flash(f'Regeneration failed: {str(e)}', 'error')
        return redirect(url_for('newsletters.newsletters'))


@actions_bp.route('/finalize-newsletter/<newsletter_id>', methods=['POST'])
def action_finalize_newsletter(newsletter_id):
    """Mark newsletter as ready for distribution"""
    try:
        newsletter_repo = get_newsletter_repo()
        newsletter = newsletter_repo.get_by_id(newsletter_id)

        if newsletter:
            newsletter_repo.update(newsletter_id, {'status': 'ready'})
            flash('Newsletter marked as ready!', 'success')
        else:
            flash('Newsletter not found', 'error')

    except Exception as e:
        flash(f'Failed to finalize: {str(e)}', 'error')
    return redirect(url_for('newsletters.newsletters'))


# ------------------------------------------------------------------
# PRESS RELEASE BULK ACTIONS
# ------------------------------------------------------------------

@actions_bp.route('/delete-releases', methods=['POST'])
def action_delete_releases():
    """
    Soft delete (archive) selected press releases.

    Accepts both release_ids (legacy) and release_urls (DynamoDB-efficient).
    """
    try:
        # Try URL-based first (efficient for DynamoDB)
        release_urls = request.form.getlist('release_urls')

        # Fallback to ID-based for backwards compatibility
        if not release_urls:
            release_ids = request.form.getlist('release_ids')
            if not release_ids:
                flash('No press releases selected', 'error')
                return redirect(url_for('press_releases.press_releases'))

            # Convert IDs to URLs (inefficient but backwards compatible)
            pr_repo = get_press_release_repo()
            release_urls = []
            for release_id in release_ids:
                release = pr_repo.get_by_id(int(release_id))
                if release:
                    release_urls.append(release.url)

        # Archive by URL (O(1) for each in DynamoDB)
        pr_repo = get_press_release_repo()
        count = 0

        for url in release_urls:
            release = pr_repo.get_by_url(url)
            if release and not release.is_deleted:
                pr_repo.soft_delete(release.url)
                count += 1

        flash(f'Archived {count} press release(s)', 'success')
    except Exception as e:
        flash(f'Error archiving releases: {str(e)}', 'error')

    return redirect(url_for('press_releases.press_releases', tab='active'))


@actions_bp.route('/restore-releases', methods=['POST'])
def action_restore_releases():
    """
    Restore archived press releases back to active.

    Accepts both release_ids (legacy) and release_urls (DynamoDB-efficient).
    """
    try:
        # Try URL-based first (efficient for DynamoDB)
        release_urls = request.form.getlist('release_urls')

        # Fallback to ID-based for backwards compatibility
        if not release_urls:
            release_ids = request.form.getlist('release_ids')
            if not release_ids:
                flash('No press releases selected', 'error')
                return redirect(url_for('press_releases.press_releases', tab='archived'))

            # Convert IDs to URLs (inefficient but backwards compatible)
            pr_repo = get_press_release_repo()
            release_urls = []
            for release_id in release_ids:
                release = pr_repo.get_by_id(int(release_id))
                if release:
                    release_urls.append(release.url)

        # Restore by URL (O(1) for each in DynamoDB)
        pr_repo = get_press_release_repo()
        count = 0

        for url in release_urls:
            release = pr_repo.get_by_url(url)
            if release and release.is_deleted:
                pr_repo.restore(release.url)
                count += 1

        flash(f'Restored {count} press release(s)', 'success')
    except Exception as e:
        flash(f'Error restoring releases: {str(e)}', 'error')

    return redirect(url_for('press_releases.press_releases', tab='archived'))
