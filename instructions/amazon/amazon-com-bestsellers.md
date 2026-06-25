# Amazon.com Bestsellers

Scrape the provided Amazon.com bestsellers or category ranking page.

Return JSON with:

```json
{
  "source_url": "...",
  "items": [
    {
      "rank": 1,
      "title": "...",
      "category_context": "...",
      "price_text": "...",
      "price_value": 0.0,
      "currency": "USD",
      "rating_text": "...",
      "rating_value": 0.0,
      "reviews_count": 0,
      "badge_text": "...",
      "product_url": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial"
  }
}
```

Collect the visible ranked products from the current page, up to 50 items. Preserve ranking order exactly as displayed. If the page is paginated or lazy-loaded, collect only what can be reached safely through normal visible interactions.

Do not bypass CAPTCHA or anti-bot screens. Record blockers in output and diagnostics.
