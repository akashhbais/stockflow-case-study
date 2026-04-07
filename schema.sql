-- StockFlow Database Schema
-- PostgreSQL

CREATE TABLE companies (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


CREATE TABLE warehouses (
    id          SERIAL PRIMARY KEY,
    company_id  INT          NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    location    TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_warehouses_company ON warehouses(company_id);


CREATE TABLE suppliers (
    id              SERIAL PRIMARY KEY,
    company_id      INT          NOT NULL REFERENCES companies(id),
    name            VARCHAR(255) NOT NULL,
    contact_email   VARCHAR(255),
    contact_phone   VARCHAR(50),
    lead_time_days  INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_suppliers_company ON suppliers(company_id);


CREATE TABLE products (
    id                   SERIAL PRIMARY KEY,
    company_id           INT            NOT NULL REFERENCES companies(id),
    supplier_id          INT            REFERENCES suppliers(id),
    sku                  VARCHAR(100)   NOT NULL,
    name                 VARCHAR(255)   NOT NULL,
    description          TEXT,
    price                NUMERIC(12,2)  NOT NULL CHECK (price >= 0),
    product_type         VARCHAR(50)    NOT NULL DEFAULT 'standard',
    low_stock_threshold  INT            NOT NULL DEFAULT 10,
    is_active            BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, sku)
);

CREATE INDEX idx_products_company  ON products(company_id);
CREATE INDEX idx_products_supplier ON products(supplier_id);


CREATE TABLE inventory (
    id            SERIAL PRIMARY KEY,
    product_id    INT  NOT NULL REFERENCES products(id),
    warehouse_id  INT  NOT NULL REFERENCES warehouses(id),
    quantity      INT  NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, warehouse_id)
);

CREATE INDEX idx_inventory_product   ON inventory(product_id);
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id);


CREATE TABLE inventory_history (
    id              SERIAL PRIMARY KEY,
    inventory_id    INT          NOT NULL REFERENCES inventory(id),
    change_type     VARCHAR(50)  NOT NULL, -- 'sale', 'restock', 'adjustment', 'transfer'
    quantity_delta  INT          NOT NULL,
    quantity_after  INT          NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inv_history_inventory ON inventory_history(inventory_id);
CREATE INDEX idx_inv_history_time      ON inventory_history(created_at);


CREATE TABLE product_bundles (
    bundle_product_id     INT  NOT NULL REFERENCES products(id),
    component_product_id  INT  NOT NULL REFERENCES products(id),
    quantity              INT  NOT NULL DEFAULT 1,
    PRIMARY KEY (bundle_product_id, component_product_id)
);
