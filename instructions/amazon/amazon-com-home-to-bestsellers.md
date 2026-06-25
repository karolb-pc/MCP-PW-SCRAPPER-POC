# Amazon.com Homepage Navigation: Bestsellers

Start from the provided Amazon.com homepage URL, not from a bestsellers deep link.

Goal:

1. Open the Amazon.com homepage.
2. If a normal cookie/consent dialog appears, handle it using ordinary visible controls.
3. Navigate through visible Amazon UI to reach the Bestsellers section or a bestsellers/category ranking page.
4. Scrape the visible ranked products.

Return JSON with:

```json
{
  "source_url": "...",
  "navigation_goal": "amazon_com_homepage_to_bestsellers",
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
    "status": "ok|blocked|partial",
    "blocked_reason": null
  }
}
```

Collect visible ranked products from the reached bestsellers page, up to 50 items. Preserve ranking order exactly as displayed.

This prompt is meant to be compared with the direct bestsellers deep-link prompt. The host metrics will measure the whole agent process, including homepage navigation, finding the bestsellers entry, waiting, scraping, and output writing.

If the Bestsellers section cannot be found through visible UI, do not guess hidden endpoints. Return a partial or blocked result explaining what was tried.

Do not bypass CAPTCHA, bot challenges, or access controls.
