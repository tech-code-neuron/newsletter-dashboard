# Press Release Pipeline

**Build your own sector newsletter for $15/month. No Bloomberg required.**

A production-ready system that monitors company press releases, enriches them with AI, and generates daily newsletter digests. Track any sector — REITs, biotech, energy, fintech — using free IR email alerts and cheap APIs instead of $25,000/year data terminals.

---

## The Problem

| Service | Annual Cost |
|---------|-------------|
| Bloomberg Terminal | $25,000+ |
| Refinitiv Eikon | $22,000+ |
| FactSet | $12,000+ |
| **This Project** | **~$180** |

Most sector tracking requires expensive data vendors. But company press releases are free — they're sent directly to anyone who signs up. This project automates the collection, enrichment, and distribution.

---

## Why I Built This

I work in banking and credit and don't have a Bloomberg or FactSet subscription. I wanted an easy way to track hundreds of companies without paying a massive subscription fee.

This tool works best for public companies — just sign up for their free IR email alerts. But there's also a mechanism to track private companies through the Brave Search API, which scans news sources for company mentions.

If you're an analyst, investor, or just someone who wants to stay informed about a sector without spending $25k/year, this is for you.

---

## How It Works

```
┌──────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  IR Email Alerts │────▶│    Parser    │────▶│   Enricher   │────▶│  Newsletter  │
│  (Free signups)  │     │  (AI match)  │     │ (Full text)  │     │   Digest     │
└──────────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
         │                                            │
         │              ┌──────────────┐              │
         └─────────────▶│ Brave Search │◀─────────────┘
                        │  (News API)  │
                        └──────────────┘
```

1. **Sign up** for free email alerts on company IR pages
2. **Forward** those emails to your pipeline (AWS SES)
3. **AI enriches** — fetches full text, categorizes (M&A, Earnings, Dividends)
4. **Daily digest** — professional newsletter ready to send

---

## What You Get

| Feature | Description |
|---------|-------------|
| **Multi-Source Aggregation** | IR emails + Brave Search + RSS feeds + SEC filings |
| **SEC 8-K/Prospectus Tracking** | Auto-ingest IPO supplements and material events |
| **AI Classification** | Claude-powered categorization with confidence scoring |
| **Smart Scraping** | Playwright fallback for JavaScript-heavy sites |
| **Newsletter Generation** | Professional HTML digests, ready for email |
| **Full Infrastructure** | Complete Terraform for one-command AWS deployment |
| **Flask Dashboard** | Web UI to manage companies and review releases |

---

## Quick Start

### Local Development

```bash
# Clone
git clone https://github.com/tech-code-neuron/newsletter-dashboard.git
cd newsletter-dashboard

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Anthropic API key

# Initialize
python core/models.py

# Run
python app.py
# Open http://localhost:5001
```

### AWS Deployment

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

terraform init
terraform apply
```

See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) for full instructions.

---

## Adapting for Your Sector

This was built for REITs but works for any sector:

### 1. Add Your Companies

Edit `config/email_parser_config.py`:
```python
COMPANY_DOMAINS = {
    "investor.yourcompany.com": "TICK",
    "ir.biotech-corp.com": "BIO",
}
```

### 2. Customize Categories

Edit `config/categories.py`:
```python
CATEGORIES = [
    "Earnings",
    "M&A",
    "Clinical Trial",    # Biotech
    "FDA Approval",      # Biotech
    "Production Update", # Energy
]
```

### 3. Sign Up for IR Alerts

Most public companies let you subscribe to press releases:
1. Go to company's Investor Relations page
2. Find "Email Alerts" or "Subscribe"
3. Forward those emails to your pipeline

See [IR_EMAIL_SETUP.md](IR_EMAIL_SETUP.md) for detailed instructions.

---

## Cost Breakdown

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| AWS Lambda | ~$0.10 | Free tier covers most usage |
| DynamoDB | ~$0.25 | On-demand, scales with usage |
| Claude API | $5-15 | ~$0.003 per classification |
| Brave Search | $0-5 | Optional, for news discovery |
| **Total** | **$5-20/month** | |

**vs. Bloomberg: $2,000/month**

---

## Architecture

### Lambda Functions

| Function | Purpose |
|----------|---------|
| `parser` | Extract metadata from emails with confidence scoring |
| `enricher` | Fetch full article content, handle redirects |
| `playwright-scraper` | Browser-based scraping for JS sites |
| `brave-news-fetcher` | Daily news discovery via Brave API |
| `8k-fetcher` | Poll SEC EDGAR for prospectus filings |
| `daily-summary` | Generate newsletter digest |

### Data Flow

- **Email ingestion**: SES → S3 → Parser Lambda
- **Enrichment**: Parser → Enricher → DynamoDB
- **Fallback**: Failed scrapes → Playwright queue
- **News**: Brave API → confidence scoring → DynamoDB

---

## Project Structure

```
├── app.py                    # Flask dashboard
├── config/                   # Configuration
│   ├── categories.py         # Press release categories
│   ├── email_parser_config.py # Company domain mappings
│   └── selectors.json        # CSS scraping selectors
├── core/                     # Business logic
│   ├── categorizer.py        # AI classification
│   ├── scraper.py            # Web scraping
│   └── newsletter_generator.py
├── infrastructure/
│   ├── lambdas/              # AWS Lambda functions
│   └── terraform/            # Infrastructure as code
├── templates/                # Flask HTML templates
└── static/                   # CSS, JS assets
```

---

## Documentation

- [GETTING_STARTED.md](GETTING_STARTED.md) — Step-by-step local setup
- [IR_EMAIL_SETUP.md](IR_EMAIL_SETUP.md) — How to set up company email alerts
- [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) — Full AWS deployment guide
- [ADAPTING_FOR_YOUR_SECTOR.md](ADAPTING_FOR_YOUR_SECTOR.md) — Customize for biotech, energy, etc.

---

## Why Open Source?

Financial data shouldn't require a $25k terminal. Press releases are public — companies want you to read them. This project proves you can build professional-grade sector tracking with:

- Free IR email signups
- Cheap AI APIs (Claude)
- Serverless AWS infrastructure
- A weekend of setup time

**Fork it. Adapt it. Track your sector.**

---

## License

MIT License — use it however you want.

---

## Keywords

`press-release-automation` `newsletter-generator` `investor-relations` `email-pipeline` `aws-lambda` `serverless` `web-scraping` `playwright` `terraform` `flask` `dynamodb` `sector-newsletter` `company-news-aggregator` `ir-monitoring` `bloomberg-alternative` `financial-data` `sec-filings`
