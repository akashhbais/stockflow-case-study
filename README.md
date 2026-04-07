# StockFlow - Backend Engineering Intern Case Study

---

## Part 1: Code Review and Debugging

### Original Code

```
POST /api/products

1. Create Product from request body
2. db.session.add(product)
3. db.session.commit()       (first commit)

4. Create Inventory using product.id
5. db.session.add(inventory)
6. db.session.commit()       (second commit)

7. return { message, product_id }
```

### Issues Found

**1. Two separate commits with no transaction**

This is the main problem. The product gets saved first, and then inventory is saved separately. If anything goes wrong between those two commits (server crash, timeout, anything), you end up with a product in the database but no inventory record for it.

In production this creates ghost products. They exist in the products table but have no stock entry. Reports break, and if someone tries to create the same product again the SKU check blocks them because the row already exists.

The fix is straightforward. Use `flush()` to get the product ID without committing, add the inventory record, then do one single `commit()` at the end. If anything fails, rollback both. Either both records exist or neither does.

**2. No input validation**

The code reads directly from the request body without checking if fields exist. A request missing `initial_quantity` or `sku` will throw a KeyError and crash with a 500 error. The client gets back a raw stack trace which exposes internal server details.

Before touching the database, check that all required fields are present and values are the right types.

**3. Price stored as float**

Floating point numbers are not reliable for money. `9.99` stored as a float can become `9.990000000001` in the database. Price should always be stored as `DECIMAL` or `NUMERIC` for exact precision.

**4. No error handling**

There is no try/catch anywhere. A duplicate SKU, missing warehouse, or database timeout would all crash the endpoint with an unhandled exception. The API should catch specific errors and return clean responses. For example, a duplicate SKU should return `409 Conflict`, not a 500.

**5. warehouse_id on the product model**

According to the requirements, products can exist across multiple warehouses. Storing `warehouse_id` on the product ties it to one warehouse at creation which breaks that. The warehouse relationship should only live in the Inventory table.

**6. Wrong HTTP status on success**

The endpoint returns 200. The correct status for creating a new resource is `201 Created`.

---

### Corrected Approach

See `part3/create_product.py` for the fixed implementation.

The key changes:
- Single transaction using `flush()` then one `commit()`
- Required field validation before any DB call
- `DECIMAL` type for price
- `try/except` catching `IntegrityError` separately for duplicate SKU (returns 409)
- Warehouse existence check before proceeding
- Returns `201` on success

---

## Part 2: Database Design

Full schema is in `schema.sql`. Here is a summary of the tables and the thinking behind them.

### Tables

**companies** - top level tenant. Everything belongs to a company.

**warehouses** - belongs to a company. A company can have many warehouses.

**suppliers** - belongs to a company. Tracks contact info and lead time for reordering.

**products** - belongs to a company, optionally linked to a supplier. Has its own `low_stock_threshold` per product because different product types have different thresholds. Uses `is_active` for soft deletes so history is never lost.

**inventory** - the join between products and warehouses. One row per product per warehouse. Holds current quantity. Has a `CHECK (quantity >= 0)` constraint.

**inventory_history** - append only log of every quantity change. Stores the delta and a snapshot of the value after the change. This is what we use to calculate sales velocity for the low stock alert.

**product_bundles** - self referencing junction table. A bundle is just a product that contains other products. Stores `(bundle_id, component_id, quantity)`.

### Key Design Decisions

**SKU is unique per company, not globally**

Two different companies might use the same SKU codes. A global unique constraint would block that. The constraint is on `(company_id, sku)` together.

**DECIMAL for price**

Already mentioned in Part 1. Floats are not safe for money.

**inventory_history is append only**

Updating the inventory quantity directly loses the history. Every change gets logged as a new row with a delta and a snapshot. This gives us time series data for sales velocity, audit trails, and the ability to reconstruct what inventory looked like at any point.

**Soft deletes with is_active**

Hard deleting a product breaks foreign key references in history. Setting `is_active = false` keeps all data intact.

**Indexes**

- `warehouses.company_id` - used on almost every query
- `products.company_id` - same reason
- `inventory_history.created_at` - needed for the 30 day sales velocity window
- `inventory.product_id` and `inventory.warehouse_id` - used in joins on the low stock query

### Questions for the Product Team

1. **Bundle pricing:** When a bundle is sold, do we deduct inventory from each component separately? Is the price set manually or calculated from components?

2. **Negative stock:** Can inventory go below zero for backorders? Right now there is a CHECK constraint preventing it but that might need to change.

3. **Warehouse transfers:** If stock moves from warehouse A to B, should that be two history entries linked together, or a separate transfers table?

4. **Historical data needs:** Do we need exact inventory at any past point, or is a 30 day rolling window enough? This affects how much we rely on the `quantity_after` snapshot.

---

## Part 3: API Implementation

**Endpoint:** `GET /api/companies/{company_id}/alerts/low-stock`

Full implementation is in `part3/low_stock.py`.

### Assumptions

- "Recent sales activity" means at least one sale in the last 30 days. Products with no recent sales are excluded because there is no demand signal so the alert is not useful.
- "Days until stockout" is `current stock / average daily sales` over 30 days. Returns null when average daily sales is zero.
- `low_stock_threshold` is stored per product in the database, not a global constant.
- Only products where `is_active = true` are included.

### Approach

The main thing I wanted to avoid was the N+1 query problem. The naive way would be to fetch all inventory rows and then loop through each one making separate queries for sales data and supplier info. For a company with hundreds of products across multiple warehouses that is hundreds of database round trips.

Instead the whole thing runs in a single query using a CTE to pre-aggregate sales data, then joins inventory, products, warehouses and suppliers together in one go.

The results are sorted by `days_until_stockout` ascending so the most urgent alerts come first. Products with null stockout (zero sales velocity) are pushed to the bottom.

### Edge Cases

- Company not found returns 404
- No alerts returns an empty array with 200, not a 404
- Products with no supplier return null for the supplier field, the alert still shows
- Division by zero when sales velocity is zero, returns null for days_until_stockout
- Database errors are logged server side, client only sees a generic 500

### Expected Response

```json
{
  "alerts": [
    {
      "product_id": 123,
      "product_name": "Widget A",
      "sku": "WID-001",
      "warehouse_id": 456,
      "warehouse_name": "Main Warehouse",
      "current_stock": 5,
      "threshold": 20,
      "days_until_stockout": 12,
      "supplier": {
        "id": 789,
        "name": "Supplier Corp",
        "contact_email": "orders@supplier.com"
      }
    }
  ],
  "total_alerts": 1
}
```
