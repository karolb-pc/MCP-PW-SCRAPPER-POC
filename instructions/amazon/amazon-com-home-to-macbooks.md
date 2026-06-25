# Amazon.com Homepage Navigation: MacBooks

Start from the provided Amazon.com homepage URL, not from a search-result deep link.

Goal:

1. Open the Amazon.com homepage.
2. If a normal cookie/consent dialog appears, handle it using ordinary visible controls.
3. Use the site search box to search for `macbook`.
4. Wait for the search results page.
5. Scrape the first visible search results.

Return JSON with:

```json
{
  "source_url": "...",
  "navigation_goal": "amazon_com_homepage_to_macbook_search",
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

Collect up to the first 24 visible product results. Keep sponsored products but mark `sponsored: true` when visible.

This prompt is meant to be compared with the direct search-results prompt. The host metrics will measure the whole agent process, including homepage navigation, search submission, waiting, scraping, and output writing.

If Amazon shows CAPTCHA, bot challenge, login wall, or an unavailable page, do not bypass it. Return `items: []`, set `meta.status` to `blocked`, and explain the blocker in both final output and diagnostics.
