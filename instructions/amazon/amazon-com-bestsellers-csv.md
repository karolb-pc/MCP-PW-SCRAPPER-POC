# Amazon.com Bestsellers CSV

Scrape the provided Amazon.com bestsellers or category ranking page.

Write the final output as RFC 4180-style CSV, not JSON. The first row must be this exact header:

```csv
rank,title,category_context,price_text,price_value,currency,rating_text,rating_value,reviews_count,badge_text,product_url,status,blocked_reason
```

Rows:

- Collect the visible ranked products from the current page, up to 50 items.
- Preserve ranking order exactly as displayed.
- If the page is paginated or lazy-loaded, collect only what can be reached safely through normal visible interactions.
- Use `USD` for `currency` when a dollar price is visible.
- Normalize `price_value`, `rating_value`, and `reviews_count` only when safe; otherwise leave the numeric cell empty.
- Preserve useful raw text in `price_text`, `rating_text`, and `badge_text`.
- Use absolute URLs in `product_url` when possible.
- Set `status` to `ok` for normal product rows.
- Set `blocked_reason` empty for normal product rows.

CSV rules:

- Do not wrap the CSV in Markdown fences.
- Escape commas, quotes, and newlines according to normal CSV rules.
- If Amazon shows CAPTCHA, bot challenge, login wall, unavailable page, or repeated navigation failure, do not bypass it. Write only the header and one blocker row with `status` set to `blocked`, `blocked_reason` explaining the blocker, and product fields left empty where unavailable.
