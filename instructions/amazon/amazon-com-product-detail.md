# Amazon.com Product Detail

Scrape one Amazon.com product detail page from the provided URL.

Return JSON with one item:

```json
{
  "source_url": "...",
  "items": [
    {
      "title": "...",
      "brand": "...",
      "asin": "...",
      "price_text": "...",
      "price_value": 0.0,
      "currency": "USD",
      "availability_text": "...",
      "delivery_text": "...",
      "seller": "...",
      "ships_from": "...",
      "rating_text": "...",
      "rating_value": 0.0,
      "reviews_count": 0,
      "feature_bullets": ["..."],
      "technical_details": {
        "...": "..."
      },
      "variant_summary": "...",
      "canonical_url": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial"
  }
}
```

Prefer visible page data. Expand standard product detail sections only when available through normal UI interaction. Do not add the product to cart. Do not log in unless credentials/session were explicitly provided by the host.
