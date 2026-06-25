# Amazon.com Prime And Availability

Scrape availability, delivery, and Prime-related information from the provided Amazon.com listing or product page.

Return JSON with:

```json
{
  "source_url": "...",
  "items": [
    {
      "title": "...",
      "price_text": "...",
      "price_value": 0.0,
      "currency": "USD",
      "availability_text": "...",
      "delivery_text": "...",
      "prime_badge": true,
      "seller": "...",
      "ships_from": "...",
      "product_url": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial"
  }
}
```

For search/listing pages, collect up to 24 visible products. For product pages, return one item. Preserve raw delivery and availability text because it is often location-dependent. If exact Prime status is ambiguous, set `prime_badge` to `null` and explain in diagnostics.
