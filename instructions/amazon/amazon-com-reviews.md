# Amazon.com Product Reviews

Scrape review data from the provided Amazon.com product or reviews URL.

Return JSON with:

```json
{
  "source_url": "...",
  "items": [
    {
      "review_position": 1,
      "review_title": "...",
      "rating_text": "...",
      "rating_value": 0.0,
      "author": "...",
      "review_date_text": "...",
      "verified_purchase": true,
      "review_text": "...",
      "helpful_text": "...",
      "variant_text": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial",
    "product_title": "..."
  }
}
```

Collect up to the first 20 visible reviews. Use normal pagination only if it is visible and safe. Do not log in, vote, sort in a way that changes account state, or bypass access controls.
