# Amazon.com Complex Budget Filtered Research

Start from the provided Amazon.com URL. Prefer starting from `https://www.amazon.com/`.

Goal:

1. Open Amazon.com.
2. If a normal cookie/consent dialog appears, handle it using ordinary visible controls.
3. Use the site search box to search for `wireless noise cancelling headphones`.
4. Inspect the search results and find products that match these criteria:
   - visible price between USD 50 and USD 150 inclusive;
   - rating at least 4.2 stars when visible;
   - at least 1,000 reviews when visible;
   - prefer Prime or clearly fast delivery when visible;
   - exclude sponsored products unless there are fewer than 5 qualifying non-sponsored products;
   - exclude accessories, replacement ear pads, cables, cases, renewed/refurbished items, and unrelated products.
5. Scroll through the search results until at least 40 product tiles have been inspected or until the page clearly stops loading new visible results.
6. Select up to 5 qualifying products, prioritizing best overall value based on price, rating, review count, delivery/Prime signal, and relevance.
7. For each selected product:
   - open the product detail page;
   - read title, brand, price, availability, delivery text, seller/ships-from if visible, rating, review count, feature bullets, color/style if visible, and technical details/specification table if visible;
   - scroll the product page if needed to reach details;
   - do not add to cart, buy, vote, log in, or perform account actions;
   - return to the result list or otherwise continue safely to the next selected product.
8. Produce a decision-style JSON output that explains why each product qualified.

Return JSON with:

```json
{
  "source_url": "...",
  "navigation_goal": "amazon_com_homepage_to_budget_filtered_search_to_product_details",
  "search_query": "wireless noise cancelling headphones",
  "filters": {
    "price_min": 50.0,
    "price_max": 150.0,
    "currency": "USD",
    "minimum_rating": 4.2,
    "minimum_reviews": 1000,
    "prefer_prime_or_fast_delivery": true,
    "prefer_non_sponsored": true
  },
  "items": [
    {
      "result_position": 1,
      "qualified": true,
      "qualification_reason": "...",
      "rejection_reason": null,
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
      "renewed_or_refurbished": false,
      "feature_bullets": ["..."],
      "technical_details": {
        "...": "..."
      },
      "product_url": "..."
    }
  ],
  "rejected_examples": [
    {
      "result_position": 1,
      "title": "...",
      "price_text": "...",
      "rating_text": "...",
      "reviews_text": "...",
      "reason": "outside_price_range|too_few_reviews|too_low_rating|accessory|sponsored_preferred_non_sponsored|unrelated|renewed_or_refurbished|missing_required_data"
    }
  ],
  "decision_summary": {
    "best_overall_title": "...",
    "best_budget_title": "...",
    "highest_rating_title": "...",
    "most_reviewed_title": "...",
    "selection_notes": ["..."]
  },
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial",
    "blocked_reason": null,
    "results_inspected_count": 0,
    "qualified_count": 0,
    "rejected_count": 0,
    "product_pages_opened_count": 0
  }
}
```

Rules:

- Keep the scrape bounded: inspect at most 40 result tiles and open at most 5 product pages.
- The `items` array should contain selected qualifying products only.
- Include up to 8 `rejected_examples` to show how the filtering decision was made.
- If no products fully match the criteria, return the best partial matches with `meta.status: "partial"` and explain which criteria were missing.
- Mark `sponsored: true` when a sponsored label is visible.
- Mark `renewed_or_refurbished: true` when the listing visibly says renewed, refurbished, pre-owned, or similar.
- Use `null` for numeric fields that cannot be safely parsed.
- Preserve raw text for price, delivery, availability, rating, and review count.
- If technical details are hidden behind normal expandable UI, expand only if it is visible and safe.
- If Amazon shows CAPTCHA, bot challenge, login wall, unavailable page, or repeated navigation failure, do not bypass it. Return a partial or blocked JSON result explaining what happened.
