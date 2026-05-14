# Getting Started

A step-by-step guide to running the Press Release Pipeline locally.

---

## Prerequisites

- Python 3.9+
- pip
- Git
- An Anthropic API key ([get one here](https://console.anthropic.com/))

---

## Step 1: Clone and Setup

```bash
# Clone the repository
git clone https://github.com/tech-code-neuron/newsletter-dashboard.git
cd newsletter-dashboard

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed Flask-2.x.x anthropic-0.x.x boto3-1.x.x ...
```

---

## Step 2: Configure Environment

```bash
# Copy example config
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:
```env
ANTHROPIC_API_KEY=sk-ant-xxxxx
FLASK_SECRET_KEY=any-random-string-here
```

---

## Step 3: Initialize Database

```bash
python core/models.py
```

**Expected output:**
```
Database initialized at data/press_releases.db
```

This creates a SQLite database for local development.

---

## Step 4: Load Sample Companies (Optional)

```bash
python scripts/load_companies.py
```

This loads pre-configured companies. Skip this if you want to add your own.

---

## Step 5: Run the Dashboard

```bash
python app.py
```

**Expected output:**
```
 * Running on http://0.0.0.0:5001
 * Debug mode: off
```

Open http://localhost:5001 in your browser.

---

## Verify It Works

### Test 1: Dashboard Loads
- Visit http://localhost:5001
- You should see the "Press Release Pipeline" dashboard
- Navigation should show: Dashboard, Companies, Press Releases

### Test 2: Add a Company
1. Click **Companies** → **Add Company**
2. Enter a ticker (e.g., "TEST") and company name
3. Save and verify it appears in the list

### Test 3: Manual Scrape (if companies loaded)
1. Click **Companies**
2. Select a company with an IR URL configured
3. Click **Scrape** to fetch recent press releases
4. Check **Press Releases** tab for results

---

## Next Steps

- **Set up email ingestion**: See [IR_EMAIL_SETUP.md](IR_EMAIL_SETUP.md)
- **Deploy to AWS**: See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)
- **Customize for your sector**: See [ADAPTING_FOR_YOUR_SECTOR.md](ADAPTING_FOR_YOUR_SECTOR.md)

---

## Troubleshooting

### "ModuleNotFoundError"
Make sure you activated the virtual environment:
```bash
source venv/bin/activate
```

### "Database not found"
Run the initialization:
```bash
python core/models.py
```

### "Invalid API key"
Check your `.env` file has the correct Anthropic key.

### Port 5001 in use
Change the port in `app.py` or kill the existing process:
```bash
lsof -i :5001  # Find the process
kill -9 <PID>  # Kill it
```
