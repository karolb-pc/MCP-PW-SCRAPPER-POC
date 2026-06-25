# Amazon.com Search: MacBooks

Scrape MacBook search results from the provided Amazon.com search results URL.

Return JSON with:

```json
{
  "source_url": "...",
  "user_prompt": "...",
  "items": [
    {
      "position": 1,
      "title": "...",
      "brand_or_series": "...",
      "price_text": "...",
      "price_value": 0.0,
      "currency": "USD",
      "rating_text": "...",
      "rating_value": 0.0,
      "reviews_count": 0,
      "availability_text": "...",
      "delivery_text": "...",
      "prime_badge": true,
      "sponsored": false,
      "product_url": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial",
    "blocked_reason": null
  }
}
```

Collect up to the first 24 organic-looking product results visible in the search listing. Keep sponsored products but mark `sponsored: true` when visible. Normalize prices and review counts when safe; otherwise keep the text and use `null` for numeric fields.

If Amazon shows CAPTCHA, bot challenge, login wall, or an unavailable page, do not bypass it. Return `items: []`, set `meta.status` to `blocked`, and explain the blocker.
