#!/usr/bin/env python3
"""
Automatic IR Email Signup Tracker

Records ALL your actions automatically:
- Every click (element, text, location)
- Every keystroke (which field, what was typed)
- Every navigation (URL changes)
- Form submissions

Minimal manual input - just press ENTER when done.
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

# Global event tracking
events = []


def load_companies():
    """Load all active companies from database."""
    session = Session()
    companies = session.query(Company).filter_by(active=True).order_by(Company.ticker).all()
    session.close()
    return companies


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


def save_page_html(page, ticker):
    """Save raw HTML for later analysis."""
    html_content = page.content()
    html_file = HTML_DIR / f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    html_file.write_text(html_content, encoding='utf-8')
    return str(html_file)


def inject_tracking_script(page_or_frame):
    """Inject tracking JavaScript into a page or frame."""
    try:
        page_or_frame.evaluate("""
        () => {
            window.capturedEvents = [];

            // Track all clicks
            document.addEventListener('click', (e) => {
                const element = e.target;
                window.capturedEvents.push({
                    type: 'click',
                    tag: element.tagName,
                    id: element.id,
                    class: element.className,
                    text: element.innerText?.substring(0, 100) || element.value || '',
                    href: element.href || null,
                    timestamp: new Date().toISOString(),
                    x: e.clientX,
                    y: e.clientY
                });
            }, true);

            // Track all input/typing
            document.addEventListener('input', (e) => {
                const element = e.target;
                window.capturedEvents.push({
                    type: 'input',
                    tag: element.tagName,
                    id: element.id,
                    name: element.name,
                    class: element.className,
                    inputType: element.type,
                    value: element.value,
                    placeholder: element.placeholder,
                    timestamp: new Date().toISOString()
                });
            }, true);

            // Track checkbox/radio changes
            document.addEventListener('change', (e) => {
                const element = e.target;
                if (element.type === 'checkbox' || element.type === 'radio') {
                    window.capturedEvents.push({
                        type: 'checkbox_change',
                        tag: element.tagName,
                        id: element.id,
                        name: element.name,
                        class: element.className,
                        checked: element.checked,
                        value: element.value,
                        label: element.labels?.[0]?.innerText || '',
                        timestamp: new Date().toISOString()
                    });
                } else if (element.tagName === 'SELECT') {
                    window.capturedEvents.push({
                        type: 'dropdown_change',
                        id: element.id,
                        name: element.name,
                        selectedValue: element.value,
                        selectedText: element.options[element.selectedIndex]?.text,
                        timestamp: new Date().toISOString()
                    });
                }
            }, true);

            // Track form submissions
            document.addEventListener('submit', (e) => {
                const form = e.target;
                const formData = new FormData(form);
                const data = {};
                for (let [key, value] of formData.entries()) {
                    data[key] = value;
                }
                window.capturedEvents.push({
                    type: 'form_submit',
                    formId: form.id,
                    formClass: form.className,
                    formAction: form.action,
                    formData: data,
                    timestamp: new Date().toISOString()
                });
            }, true);
        }
    """)
    except Exception as e:
        print(f"Warning: Could not inject tracking script: {e}")


def setup_event_tracking(page):
    """Set up automatic event tracking on the page."""
    global events
    events = []  # Reset for each company

    # Inject into main page
    inject_tracking_script(page)

    # Re-inject on every navigation (when user clicks to new pages)
    def on_navigation(frame):
        events.append({
            'type': 'navigation',
            'url': frame.url,
            'timestamp': datetime.now().isoformat()
        })
        # Re-inject tracking script on new page
        page.wait_for_timeout(1000)  # Wait for page to load
        inject_tracking_script(frame)

        # Also inject into any iframes on the new page
        try:
            for iframe in frame.child_frames:
                inject_tracking_script(iframe)
        except:
            pass

    page.on("framenavigated", on_navigation)

    # Also inject into existing iframes
    try:
        for iframe in page.frames[1:]:  # Skip main frame
            inject_tracking_script(iframe)
    except:
        pass


def get_captured_events(page):
    """Retrieve all captured events from the page and all iframes."""
    global events

    js_events = []

    # Get events from main page
    try:
        main_events = page.evaluate("() => window.capturedEvents || []")
        js_events.extend(main_events)
    except:
        pass

    # Get events from all iframes
    try:
        for frame in page.frames:
            try:
                frame_events = frame.evaluate("() => window.capturedEvents || []")
                if frame_events:
                    js_events.extend(frame_events)
            except:
                continue
    except:
        pass

    # Combine with navigation events
    all_events = events + js_events

    # Sort by timestamp
    all_events.sort(key=lambda x: x.get('timestamp', ''))

    return all_events


def analyze_events(events):
    """Analyze captured events to extract useful patterns."""
    analysis = {
        'clicks': [],
        'navigation_path': [],
        'form_fields': [],
        'checkboxes': [],
        'dropdowns': [],
        'form_submission': None
    }

    for event in events:
        event_type = event.get('type')

        if event_type == 'click':
            analysis['clicks'].append({
                'text': event.get('text', '').strip(),
                'tag': event.get('tag'),
                'href': event.get('href'),
                'timestamp': event.get('timestamp')
            })

        elif event_type == 'navigation':
            analysis['navigation_path'].append({
                'url': event.get('url'),
                'timestamp': event.get('timestamp')
            })

        elif event_type == 'input':
            field = {
                'id': event.get('id'),
                'name': event.get('name'),
                'type': event.get('inputType'),
                'value': event.get('value'),
                'placeholder': event.get('placeholder')
            }
            # Don't duplicate
            if field not in analysis['form_fields']:
                analysis['form_fields'].append(field)

        elif event_type == 'checkbox_change':
            analysis['checkboxes'].append({
                'id': event.get('id'),
                'name': event.get('name'),
                'label': event.get('label'),
                'checked': event.get('checked'),
                'value': event.get('value')
            })

        elif event_type == 'dropdown_change':
            analysis['dropdowns'].append({
                'id': event.get('id'),
                'name': event.get('name'),
                'selected_value': event.get('selectedValue'),
                'selected_text': event.get('selectedText')
            })

        elif event_type == 'form_submit':
            analysis['form_submission'] = {
                'form_id': event.get('formId'),
                'form_action': event.get('formAction'),
                'form_data': event.get('formData')
            }

    return analysis


def interactive_signup_session():
    """Main interactive session with automatic tracking."""
    companies = load_companies()
    knowledge = load_knowledge_base()

    print(f"\n{'='*60}")
    print(f"IR Email Signup Automatic Tracker")
    print(f"{'='*60}")
    print(f"Total companies to document: {len(companies)}")
    print(f"Already documented: {len(knowledge)}")
    print(f"\nThis script automatically tracks:")
    print(f"  ✓ Every click you make")
    print(f"  ✓ Every field you type in")
    print(f"  ✓ Every checkbox you check")
    print(f"  ✓ Every dropdown you select")
    print(f"  ✓ Every page you navigate to")
    print(f"\nJust sign up normally - I'll record everything!")
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
                print(f"\nOpening IR page and starting event tracking...")
                page.goto(company.ir_url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(2000)  # Let page settle

                # Set up automatic event tracking
                setup_event_tracking(page)

                # Wait for user to complete signup
                print(f"\n{'─'*60}")
                print(f"SIGN UP for email notifications now.")
                print(f"I'm recording every action you take...")
                print(f"Press ENTER when done, or 's' to skip this company")
                print(f"{'─'*60}")
                user_input = input("> ").strip().lower()

                if user_input == 's':
                    print(f"Skipped {ticker}")
                    continue

                # Capture final state
                print(f"\nCapturing data...")
                current_url = page.url
                captured_events = get_captured_events(page)
                event_analysis = analyze_events(captured_events)
                html_file = save_page_html(page, ticker)

                # Minimal questions - just confirmation
                print(f"\n{'─'*60}")
                print(f"RECORDED {len(captured_events)} EVENTS:")
                print(f"  - Clicks: {len(event_analysis['clicks'])}")
                print(f"  - Form fields: {len(event_analysis['form_fields'])}")
                print(f"  - Checkboxes: {len(event_analysis['checkboxes'])}")
                print(f"  - Pages visited: {len(event_analysis['navigation_path'])}")
                print(f"{'─'*60}")

                success = input("\nDid signup succeed? (y/n): ").strip().lower() == 'y'
                notes = input("Any notes? (or press Enter to skip): ").strip()

                # Combine all data
                company_data = {
                    'ticker': ticker,
                    'company_name': company.name,
                    'ir_url': company.ir_url,
                    'final_signup_url': current_url,
                    'url_changed': current_url != company.ir_url,
                    'timestamp': datetime.now().isoformat(),
                    'html_snapshot': html_file,
                    'captured_events': captured_events,
                    'event_analysis': event_analysis,
                    'signup_successful': success,
                    'notes': notes
                }

                # Save to knowledge base
                knowledge[ticker] = company_data
                save_knowledge_base(knowledge)

                print(f"\n✓ Saved {len(captured_events)} events for {ticker}")

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


if __name__ == "__main__":
    interactive_signup_session()
