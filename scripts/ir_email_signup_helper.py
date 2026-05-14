#!/usr/bin/env python3
"""
Interactive IR Email Signup Documentation Helper

Helps document manual email signups to build a knowledge base for automation.
Opens each company's IR page, waits for you to sign up, then captures detailed
page structure and form elements.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Company

# Database setup
DATABASE_URL = "sqlite:///data/reit_newsletter.db"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# Output paths
KNOWLEDGE_FILE = "ir_signup_knowledge.json"
HTML_DIR = Path("ir_signup_html")
HTML_DIR.mkdir(exist_ok=True)


def load_companies():
    """Load all active companies from database."""
    session = Session()
    companies = session.query(Company).filter_by(active=True).order_by(Company.ticker).all()
    session.close()
    return companies


def extract_email_fields(page):
    """Extract all potential email input fields."""
    fields = []

    # Find all input elements that could be email fields
    selectors = [
        'input[type="email"]',
        'input[name*="email" i]',
        'input[id*="email" i]',
        'input[placeholder*="email" i]',
        'input[aria-label*="email" i]'
    ]

    for selector in selectors:
        elements = page.query_selector_all(selector)
        for elem in elements:
            field_data = {
                'tag': elem.evaluate('el => el.tagName.toLowerCase()'),
                'type': elem.get_attribute('type'),
                'id': elem.get_attribute('id'),
                'name': elem.get_attribute('name'),
                'class': elem.get_attribute('class'),
                'placeholder': elem.get_attribute('placeholder'),
                'aria_label': elem.get_attribute('aria-label'),
                'required': elem.get_attribute('required') is not None,
                'css_selector': selector
            }
            # Avoid duplicates
            if field_data not in fields:
                fields.append(field_data)

    return fields


def extract_form_container(page):
    """Extract form element details."""
    forms = []
    form_elements = page.query_selector_all('form')

    for form in form_elements:
        # Check if form contains email-related inputs
        has_email = form.query_selector('input[type="email"], input[name*="email" i]') is not None

        if has_email:
            form_data = {
                'tag': 'form',
                'id': form.get_attribute('id'),
                'class': form.get_attribute('class'),
                'action': form.get_attribute('action'),
                'method': form.get_attribute('method'),
                'name': form.get_attribute('name')
            }
            forms.append(form_data)

    return forms


def extract_checkboxes(page):
    """Extract all checkbox inputs."""
    checkboxes = []
    checkbox_elements = page.query_selector_all('input[type="checkbox"]')

    for cb in checkbox_elements:
        # Try to find associated label
        cb_id = cb.get_attribute('id')
        label_text = None

        if cb_id:
            label = page.query_selector(f'label[for="{cb_id}"]')
            if label:
                label_text = label.inner_text().strip()

        # If no label via 'for', check if checkbox is inside a label
        if not label_text:
            parent_label = cb.evaluate('el => el.closest("label")')
            if parent_label:
                label_text = cb.evaluate('el => el.closest("label").textContent').strip()

        checkbox_data = {
            'id': cb_id,
            'name': cb.get_attribute('name'),
            'value': cb.get_attribute('value'),
            'class': cb.get_attribute('class'),
            'label_text': label_text,
            'checked': cb.is_checked(),
            'required': cb.get_attribute('required') is not None
        }
        checkboxes.append(checkbox_data)

    return checkboxes


def extract_submit_button(page):
    """Extract submit buttons."""
    buttons = []

    # Find submit buttons
    submit_elements = page.query_selector_all('button[type="submit"], input[type="submit"]')

    for btn in submit_elements:
        button_data = {
            'tag': btn.evaluate('el => el.tagName.toLowerCase()'),
            'type': btn.get_attribute('type'),
            'id': btn.get_attribute('id'),
            'class': btn.get_attribute('class'),
            'name': btn.get_attribute('name'),
            'text': btn.inner_text().strip() if btn.evaluate('el => el.tagName') == 'BUTTON' else btn.get_attribute('value')
        }
        buttons.append(button_data)

    return buttons


def extract_hidden_fields(page):
    """Extract hidden input fields."""
    hidden_fields = []
    hidden_elements = page.query_selector_all('input[type="hidden"]')

    for hidden in hidden_elements:
        hidden_data = {
            'name': hidden.get_attribute('name'),
            'value': hidden.get_attribute('value'),
            'id': hidden.get_attribute('id')
        }
        hidden_fields.append(hidden_data)

    return hidden_fields


def detect_iframes(page):
    """Detect iframes that might contain signup forms."""
    iframes = []
    iframe_elements = page.query_selector_all('iframe')

    for iframe in iframe_elements:
        src = iframe.get_attribute('src')
        iframe_data = {
            'src': src,
            'id': iframe.get_attribute('id'),
            'class': iframe.get_attribute('class'),
            'name': iframe.get_attribute('name')
        }
        iframes.append(iframe_data)

    return iframes


def extract_dropdowns(page):
    """Extract select/dropdown elements."""
    dropdowns = []
    select_elements = page.query_selector_all('select')

    for select in select_elements:
        options = []
        option_elements = select.query_selector_all('option')

        for opt in option_elements:
            options.append({
                'text': opt.inner_text().strip(),
                'value': opt.get_attribute('value'),
                'selected': opt.get_attribute('selected') is not None
            })

        # Find associated label
        select_id = select.get_attribute('id')
        label_text = None

        if select_id:
            label = page.query_selector(f'label[for="{select_id}"]')
            if label:
                label_text = label.inner_text().strip()

        dropdown_data = {
            'id': select_id,
            'name': select.get_attribute('name'),
            'class': select.get_attribute('class'),
            'label_text': label_text,
            'options': options,
            'required': select.get_attribute('required') is not None
        }
        dropdowns.append(dropdown_data)

    return dropdowns


def detect_captcha(page):
    """Detect CAPTCHA elements."""
    captcha_info = {'has_captcha': False, 'type': None}

    # Check for reCAPTCHA
    if page.query_selector('.g-recaptcha, [data-sitekey]'):
        captcha_info['has_captcha'] = True
        captcha_info['type'] = 'reCAPTCHA'

    # Check for hCaptcha
    if page.query_selector('.h-captcha'):
        captcha_info['has_captcha'] = True
        captcha_info['type'] = 'hCaptcha'

    return captcha_info


def extract_context_clues(page):
    """Extract nearby text and platform indicators."""
    context = {
        'page_title': page.title(),
        'nearby_headings': [],
        'platform_indicators': {
            'scripts': [],
            'likely_platform': None
        }
    }

    # Extract headings that might indicate signup sections
    headings = page.query_selector_all('h1, h2, h3, h4')
    for h in headings:
        text = h.inner_text().strip().lower()
        if any(keyword in text for keyword in ['email', 'alert', 'subscribe', 'newsletter', 'notification', 'investor']):
            context['nearby_headings'].append(h.inner_text().strip())

    # Detect platform from scripts and URLs
    scripts = page.query_selector_all('script[src]')
    for script in scripts:
        src = script.get_attribute('src')
        if src:
            context['platform_indicators']['scripts'].append(src)

            # Platform detection
            if 'q4web.com' in src or 'q4cdn.com' in src:
                context['platform_indicators']['likely_platform'] = 'Q4'
            elif 'gcs-web.com' in src:
                context['platform_indicators']['likely_platform'] = 'GCS'
            elif 'irw.inc' in src or 'investorroom' in src:
                context['platform_indicators']['likely_platform'] = 'IRW'

    return context


def detect_trigger_elements(page):
    """Detect buttons/links that might trigger signup form (modals, etc.)."""
    triggers = []

    # Look for buttons/links with signup-related text
    keywords = ['subscribe', 'email alert', 'sign up', 'newsletter', 'investor alert', 'notifications']

    for keyword in keywords:
        elements = page.query_selector_all(f'button:has-text("{keyword}"), a:has-text("{keyword}")')
        for elem in elements[:3]:  # Limit to first 3 matches per keyword
            trigger_data = {
                'tag': elem.evaluate('el => el.tagName.toLowerCase()'),
                'text': elem.inner_text().strip(),
                'id': elem.get_attribute('id'),
                'class': elem.get_attribute('class'),
                'href': elem.get_attribute('href') if elem.evaluate('el => el.tagName') == 'A' else None
            }
            if trigger_data not in triggers:
                triggers.append(trigger_data)

    return triggers


def extract_all_data(page):
    """Extract all data from current page."""
    return {
        'email_fields': extract_email_fields(page),
        'forms': extract_form_container(page),
        'checkboxes': extract_checkboxes(page),
        'submit_buttons': extract_submit_button(page),
        'hidden_fields': extract_hidden_fields(page),
        'iframes': detect_iframes(page),
        'dropdowns': extract_dropdowns(page),
        'captcha': detect_captcha(page),
        'context': extract_context_clues(page),
        'trigger_elements': detect_trigger_elements(page)
    }


def save_page_html(page, ticker):
    """Save raw HTML for later analysis."""
    html_content = page.content()
    html_file = HTML_DIR / f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    html_file.write_text(html_content, encoding='utf-8')
    return str(html_file)


def load_knowledge_base():
    """Load existing knowledge base or create new one."""
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_knowledge_base(knowledge):
    """Save knowledge base to file."""
    with open(KNOWLEDGE_FILE, 'w') as f:
        json.dump(knowledge, indent=2, fp=f)


def ask_user_questions(original_url, current_url):
    """Ask user to verify/provide additional context."""
    questions = {}

    print("\n" + "="*60)
    print("Please answer a few questions about the signup:")
    print("="*60)

    # Success
    questions['signup_successful'] = input("Did you successfully sign up? (y/n): ").strip().lower() == 'y'

    if not questions['signup_successful']:
        questions['skip_reason'] = input("Why not? (no form found / captcha / error / other): ").strip()
        return questions

    # Navigation tracking
    if current_url != original_url:
        print(f"\nI notice you navigated away from the original IR page.")
        print(f"  Original: {original_url}")
        print(f"  Current:  {current_url}")
        questions['navigated_away'] = True
        questions['navigation_path'] = input("How did you get here? (describe clicks/links): ").strip()
    else:
        questions['navigated_away'] = input("\nDid you navigate to other pages before signing up? (y/n): ").strip().lower() == 'y'
        if questions['navigated_away']:
            questions['navigation_path'] = input("Describe the navigation path: ").strip()
        else:
            questions['navigation_path'] = "Signup on IR page directly"

    # Location
    print("\nWhere was the signup form located?")
    print("  1 = Header/Top of page")
    print("  2 = Right sidebar")
    print("  3 = Left sidebar")
    print("  4 = Modal/Popup")
    print("  5 = Footer/Bottom of page")
    print("  6 = Middle of page content")
    location_map = {'1': 'header', '2': 'right_sidebar', '3': 'left_sidebar',
                    '4': 'modal', '5': 'footer', '6': 'middle_content'}
    location_input = input("Location (1-6): ").strip()
    questions['form_location'] = location_map.get(location_input, 'unknown')

    # Trigger
    questions['required_trigger'] = input("Did you have to click something to reveal the form? (y/n): ").strip().lower() == 'y'
    if questions['required_trigger']:
        questions['trigger_description'] = input("What did you click? (button text/link text): ").strip()

    # Checkboxes
    cb_input = input("What did you check? (all/press-releases/earnings/sec-filings/none/other): ").strip().lower()
    questions['checkboxes_checked'] = cb_input

    # Dropdowns
    questions['dropdown_selections'] = input("Any dropdown selections? (describe or press Enter to skip): ").strip()

    # Success message
    questions['success_message'] = input("What success message appeared? (or press Enter if none): ").strip()

    # Notes
    questions['notes'] = input("Any other notes/observations? (or press Enter to skip): ").strip()

    return questions


def interactive_signup_session():
    """Main interactive session."""
    companies = load_companies()
    knowledge = load_knowledge_base()

    print(f"\n{'='*60}")
    print(f"IR Email Signup Documentation Helper")
    print(f"{'='*60}")
    print(f"Total companies to document: {len(companies)}")
    print(f"Already documented: {len(knowledge)}")
    print(f"\nFor each company:")
    print(f"  1. Browser will open to IR page")
    print(f"  2. Manually sign up for email alerts")
    print(f"  3. Press ENTER when done (or 's' to skip)")
    print(f"  4. Answer quick questions")
    print(f"  5. Move to next company")
    print(f"\nType 'start' and press ENTER to begin: ", end='')
    start_cmd = input().strip().lower()
    if start_cmd != 'start':
        print("Exiting...")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        for idx, company in enumerate(companies, 1):
            ticker = company.ticker

            # Skip if already documented
            if ticker in knowledge:
                print(f"\n[{idx}/{len(companies)}] {ticker} - Already documented, skipping...")
                continue

            print(f"\n{'='*60}")
            print(f"[{idx}/{len(companies)}] {ticker} - {company.name}")
            print(f"{'='*60}")
            print(f"IR URL: {company.ir_url}")

            try:
                # Navigate to IR page
                print(f"\nOpening IR page...")
                page.goto(company.ir_url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(2000)  # Let page settle

                # Wait for user to complete signup
                print(f"\n{'─'*60}")
                print(f"SIGN UP for email notifications now.")
                print(f"Press ENTER when done, or 's' to skip this company")
                print(f"{'─'*60}")
                user_input = input("> ").strip().lower()

                if user_input == 's':
                    print(f"Skipped {ticker}")
                    continue

                # Capture page state and current URL
                print(f"\nCapturing page data...")
                current_url = page.url
                extracted_data = extract_all_data(page)
                html_file = save_page_html(page, ticker)

                # Ask user questions (pass URLs for navigation tracking)
                user_answers = ask_user_questions(company.ir_url, current_url)

                # Combine all data
                company_data = {
                    'ticker': ticker,
                    'company_name': company.name,
                    'ir_url': company.ir_url,
                    'final_signup_url': current_url,
                    'url_changed': current_url != company.ir_url,
                    'timestamp': datetime.now().isoformat(),
                    'html_snapshot': html_file,
                    'extracted': extracted_data,
                    'user_input': user_answers
                }

                # Save to knowledge base
                knowledge[ticker] = company_data
                save_knowledge_base(knowledge)

                print(f"\n✓ Saved documentation for {ticker}")
                print(f"  - Email fields found: {len(extracted_data['email_fields'])}")
                print(f"  - Forms found: {len(extracted_data['forms'])}")
                print(f"  - Checkboxes found: {len(extracted_data['checkboxes'])}")
                print(f"  - Iframes found: {len(extracted_data['iframes'])}")
                print(f"  - CAPTCHA: {'Yes' if extracted_data['captcha']['has_captcha'] else 'No'}")
                if current_url != company.ir_url:
                    print(f"  - Navigation: Signup on different page (captured)")

            except Exception as e:
                print(f"\n✗ Error with {ticker}: {e}")
                print(f"Continue anyway? (y/n): ", end='')
                if input().strip().lower() != 'y':
                    break

        browser.close()

    print(f"\n{'='*60}")
    print(f"Documentation Complete!")
    print(f"{'='*60}")
    print(f"Total documented: {len(knowledge)} companies")
    print(f"Knowledge base saved to: {KNOWLEDGE_FILE}")
    print(f"HTML snapshots saved to: {HTML_DIR}/")


if __name__ == "__main__":
    interactive_signup_session()
