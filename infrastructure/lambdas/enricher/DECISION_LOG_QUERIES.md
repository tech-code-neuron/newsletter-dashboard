# URL Selection Decision Log Queries

**Log Retention**: 180 days
**Location**: CloudWatch Logs → `/aws/lambda/reitsheet-enricher`
**Query Tool**: CloudWatch Logs Insights

---

## Quick Start

Go to: [CloudWatch Logs Insights](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:logs-insights)

Select log group: `/aws/lambda/reitsheet-enricher`

---

## Common Queries

### 1. **View All Decisions for a Ticker**

Find all URL selection decisions for a specific company:

```sql
fields @timestamp, outcome.selected_url, outcome.winning_score, outcome.num_candidates
| filter event_type = "url_selection_decision"
| filter ticker = "RHP"
| sort @timestamp desc
| limit 100
```

### 2. **Find Low-Confidence Decisions**

Decisions where the score spread is small (close call):

```sql
fields @timestamp, ticker, outcome.selected_url, outcome.score_spread, outcome.winning_score
| filter event_type = "url_selection_decision"
| filter outcome.score_spread < 300
| sort outcome.score_spread asc
| limit 50
```

**Why this matters**: Score spread < 300 means two URLs were very close. Review these to see if model is uncertain.

### 3. **When Did We Pick a Landing Page?**

Find cases where the selected URL is a landing page (possible errors):

```sql
fields @timestamp, ticker, outcome.selected_url, candidate_urls
| filter event_type = "url_selection_decision"
| filter candidate_urls.0.selected = true and candidate_urls.0.signals.is_landing_page = true
| sort @timestamp desc
| limit 50
```

**Goal**: This should be <5% of decisions. If higher, model needs tuning.

### 4. **Decisions by Selection Method**

See breakdown of how URLs are being selected:

```sql
fields outcome.selection_method
| filter event_type = "url_selection_decision"
| stats count() by outcome.selection_method
```

**Expected results**:
- `smart_scoring`: ~70% (landing page detected, scored all URLs)
- `simple_first_non_landing`: ~25% (first URL was good)
- `fallback_first_url`: <5% (no domain match, used first)

### 5. **Find Decisions with DB Match Penalty**

URLs that exactly matched database `press_release_url` (usually landing pages):

```sql
fields @timestamp, ticker, outcome.selected_url, candidate_urls
| filter event_type = "url_selection_decision"
| filter candidate_urls.*.signals.is_db_match = true
| limit 50
```

### 6. **Average Score by Ticker**

Which tickers have the highest/lowest winning scores:

```sql
fields ticker, outcome.winning_score
| filter event_type = "url_selection_decision"
| stats avg(outcome.winning_score) as avg_score, count() as decisions by ticker
| sort avg_score desc
```

### 7. **Model Performance Over Time**

Daily decision counts and average scores:

```sql
fields @timestamp, outcome.winning_score
| filter event_type = "url_selection_decision"
| stats count() as decisions,
        avg(outcome.winning_score) as avg_score,
        min(outcome.winning_score) as min_score,
        max(outcome.winning_score) as max_score
  by bin(@timestamp, 1d)
| sort @timestamp desc
```

### 8. **Signal Contribution Analysis**

See how much each signal contributes on average:

```sql
fields candidate_urls.0.signal_contributions.subject_matches as subject,
       candidate_urls.0.signal_contributions.path_depth as depth,
       candidate_urls.0.signal_contributions.landing_page_penalty as landing
| filter event_type = "url_selection_decision"
| filter candidate_urls.0.selected = true
| stats avg(subject) as avg_subject_contribution,
        avg(depth) as avg_depth_contribution,
        avg(landing) as avg_landing_penalty
```

**Use this to**: Determine if weights are balanced (e.g., is subject_match dominating too much?)

### 9. **Find Decisions Where 2nd Place Was Close**

See when the runner-up almost won (score difference < 100):

```sql
fields @timestamp, ticker,
       candidate_urls.0.score as winner_score,
       candidate_urls.1.score as runnerup_score,
       candidate_urls.0.url as winner,
       candidate_urls.1.url as runnerup
| filter event_type = "url_selection_decision"
| filter (candidate_urls.0.score - candidate_urls.1.score) < 100
| sort @timestamp desc
| limit 50
```

### 10. **Extract Full Decision for Debugging**

Get complete decision log for analysis:

```sql
fields @message
| filter event_type = "url_selection_decision"
| filter ticker = "RHP"
| filter @timestamp > ago(7d)
| limit 1
```

Then copy the JSON and paste into a JSON formatter.

---

## Analysis Workflows

### Weekly Review: Model Health Check

Run these queries every week:

1. **Decision count**: Should be ~7-10 per company per week
   ```sql
   fields ticker | filter event_type = "url_selection_decision"
   | stats count() by ticker | sort count desc
   ```

2. **Landing page selection rate**: Should be <5%
   ```sql
   fields candidate_urls.0.signals.is_landing_page as is_landing
   | filter event_type = "url_selection_decision" and candidate_urls.0.selected = true
   | stats count() by is_landing
   ```

3. **Low confidence rate**: Score spread <300 should be <10%
   ```sql
   fields outcome.score_spread
   | filter event_type = "url_selection_decision"
   | stats count(*) as total,
           count_if(outcome.score_spread < 300) as low_confidence,
           count_if(outcome.score_spread < 300) / count(*) * 100 as low_confidence_pct
   ```

### Monthly Review: Weight Tuning

1. Export last 1000 decisions to CSV
2. Analyze in spreadsheet:
   - Which signal contributes most? (Should be subject_matches)
   - Are penalties too harsh? (Landing page penalty stopping good URLs?)
   - Do we need new signals? (e.g., URL contains date?)

3. Test new weights:
   - Update constants.py
   - Deploy to test environment
   - Compare results with old model

---

## Advanced: Export to S3 for Analysis

For long-term analysis beyond 180 days:

```bash
# Create S3 bucket
aws s3 mb s3://reitsheet-decision-logs

# Export logs to S3 (via CloudWatch console or CLI)
# Then query with Athena for historical analysis
```

---

## Debugging Example

**Problem**: "Why did RHP select the wrong URL on March 10?"

**Steps**:
1. Find the decision:
   ```sql
   fields @timestamp, @message
   | filter ticker = "RHP" and @timestamp >= "2026-03-10" and @timestamp < "2026-03-11"
   | filter event_type = "url_selection_decision"
   ```

2. Look at candidate_urls array:
   - Which URL won?
   - What was its score?
   - What were the runner-up scores?

3. Look at signal_contributions:
   - Did subject_matches fail? (0 matches?)
   - Was landing_page_penalty applied incorrectly?
   - Was path_depth too shallow?

4. Fix the root cause:
   - Add company to normalized_name table (if name matching failed)
   - Adjust penalty weights (if landing page was picked)
   - Update DB press_release_url (if DB match penalty applied incorrectly)

---

## What to Track Monthly

Create a dashboard tracking:
- **Total decisions**: Should grow steadily
- **Landing page selection rate**: Should stay <5%
- **Average winning score**: Should stay >500
- **Low confidence rate**: Should stay <10%
- **Fallback rate**: Should stay <5%

If any metric degrades, investigate with the queries above.
