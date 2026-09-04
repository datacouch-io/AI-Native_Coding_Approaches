# Extraction schema: purchase-order lines

Each input is one free-text purchase-order line. Extract exactly these six fields.

```json
{
  "po_number":        "string  - digits only, no PO/# prefix, no leading zeros stripped",
  "item":             "string  - the product name as written, trimmed",
  "quantity":         "integer - number of units; words like 'a dozen' become numbers",
  "unit_price_cents": "integer - price PER UNIT in whole cents (e.g. $3.50 -> 350)",
  "ship_date":        "string  - ISO 8601 YYYY-MM-DD, or null if the line gives no date",
  "account":          "string  - the account code, UPPERCASE"
}
```

## Normalisation rules

1. `po_number` is the digits only: `PO#4471`, `po 4471` and `P.O. 4471` all give `"4471"`.
2. `quantity` is an integer. Number words are converted: `a dozen` = 12, `three` = 3,
   `a pair of` = 2.
3. `unit_price_cents` is **per unit**, in cents, as an integer. `$3.50` -> `350`,
   `1.05` -> `105`, `$1,250.00` -> `125000`. If a line gives a **total** for the whole
   order rather than a unit price, divide by the quantity.
4. `ship_date` is ISO. When the year is not written, assume **2026**. Month names may be
   abbreviated. If the line gives no ship date at all, use `null`.
5. `account` is uppercased exactly as written otherwise: `acme-eu` -> `ACME-EU`.
6. `item` keeps the product name only - drop quantities, prices and packaging words.

Output a single JSON object per input. No prose, no markdown fence.
