# Brave News Fetcher Lambda

Searches Brave API daily for private company press releases from PR newswires (BusinessWire, GlobeNewswire, PRNewswire).

## How It Works

1. Fetches all private companies from `reitsheet-companies-config`
2. For each company, searches Brave API for today's press releases
3. Calculates confidence score based on company name matching
4. **>=75% confidence**: Saves to `reitsheet-reit-news-v2` (press releases table)
5. **<75% confidence**: Saves to `reitsheet-manual-review` for human review

## Confidence Scoring

| Factor | Points |
|--------|--------|
| Exact company name in title | +50 |
| Company name in URL path | +25 |
| Company name in description | +15 |
| Domain is PR newswire | +10 |

Threshold: **75%** (configurable via `CONFIDENCE_THRESHOLD` env var)

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `COMPANIES_TABLE` | DynamoDB table for companies | `reitsheet-companies-config` |
| `REIT_NEWS_TABLE` | DynamoDB table for press releases | `reitsheet-reit-news-v2` |
| `MANUAL_REVIEW_TABLE` | DynamoDB table for low-confidence items | `reitsheet-manual-review` |
| `CONFIDENCE_THRESHOLD` | Minimum confidence % for auto-ingestion | `75` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Schedule

Runs daily at **8:30am ET** via EventBridge:
```
cron(30 12 ? * * *)   # 12:30 UTC = 8:30am ET (EDT)
```

## Rate Limiting

Brave API allows 1 request/second. Lambda includes 1-second delay between company searches.

## Manual Invocation

Test with a specific date:
```bash
aws lambda invoke \
  --function-name reitsheet-brave-news-fetcher \
  --payload '{"search_date": "2026-03-31"}' \
  response.json
```

## Deployment

```bash
python3 scripts/deploy_lambda.py brave-news-fetcher --validate --zip brave-news-fetcher.zip
python3 scripts/deploy_lambda.py brave-news-fetcher --deploy --zip brave-news-fetcher.zip
```
