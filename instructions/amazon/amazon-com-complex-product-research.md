# Amazon.com Complex Product Research

Start from the provided Amazon.com URL. Prefer starting from `https://www.amazon.com/`.

Goal:

1. Open Amazon.com.
2. If a normal cookie/consent dialog appears, handle it using ordinary visible controls.
3. Use the site search box to search for `27 inch 4k monitor`.
4. Wait for the search results page.
5. Scroll through the search results until at least 30 product tiles have been inspected or until the page clearly stops loading new visible results.
6. Select up to 5 promising non-sponsored or clearly relevant products from the visible results.
7. For each selected product:
   - open the product detail page;
   - read title, price, availability, delivery text, seller/ships-from if visible, rating, review count, feature bullets, and technical details/specification table if visible;
   - scroll the product page if needed to reach technical details;
   - do not add to cart, buy, vote, log in, or perform account actions;
   - return to the result list or otherwise continue safely to the next selected product.
8. Produce a comparison-style JSON output.

Return JSON with:

```json
{
  "source_url": "...",
  "navigation_goal": "amazon_com_homepage_to_search_results_to_product_details",
  "search_query": "27 inch 4k monitor",
  "items": [
    {
      "result_position": 1,
      "title": "...",
      "brand_or_series": "...",
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
      "prime_badge": true,
      "sponsored": false,
      "feature_bullets": ["..."],
      "technical_details": {
        "...": "..."
      },
      "product_url": "..."
    }
  ],
  "comparison_summary": {
    "best_price_title": "...",
    "highest_rating_title": "...",
    "most_reviewed_title": "...",
    "notable_tradeoffs": ["..."]
  },
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial",
    "blocked_reason": null,
    "results_inspected_count": 0,
    "product_pages_opened_count": 0
  }
}
```

Rules:

- Keep the scrape bounded: inspect at most 30 result tiles and open at most 5 product pages.
- Prefer relevant monitor products over accessories, ads, warranties, unrelated stands, cables, or bundles.
- Mark `sponsored: true` when a sponsored label is visible.
- Use `null` for numeric fields that cannot be safely parsed.
- Preserve raw text for price, delivery, availability, and rating.
- If a product page opens in a new tab/window, handle it normally and keep the workflow bounded.
- If technical details are hidden behind normal expandable UI, expand only if it is visible and safe.
- If Amazon shows CAPTCHA, bot challenge, login wall, unavailable page, or repeated navigation failure, do not bypass it. Return a partial or blocked JSON result explaining what happened.
