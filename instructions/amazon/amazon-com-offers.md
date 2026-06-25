# Amazon.com Product Offers

Scrape seller/offer information for the provided Amazon.com product URL.

Return JSON with:

```json
{
  "source_url": "...",
  "items": [
    {
      "seller": "...",
      "condition": "new|used|unknown",
      "price_text": "...",
      "price_value": 0.0,
      "currency": "USD",
      "delivery_text": "...",
      "ships_from": "...",
      "seller_rating_text": "...",
      "offer_url": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial",
    "product_title": "..."
  }
}
```

If the page has a normal visible "other sellers" or offer listing entry point, open it and collect visible offers. Do not purchase, add to cart, or perform account actions. If offers are not visible or the page blocks access, return a structured partial or blocked result.
