-- ============================================================
-- Dynamic Pricing Application — ScyllaDB Schema
-- ============================================================

CREATE KEYSPACE IF NOT EXISTS pricing
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3};

USE pricing;

-- ------------------------------------------------------------
-- Product catalog - basic metadata (read-heavy, write once)
CREATE TABLE IF NOT EXISTS product (
    id           UUID PRIMARY KEY,
    ean_code     TEXT,
    sku_name     TEXT,
    seller_name  TEXT,
    description  TEXT,
    category     TEXT,
    cur_price    DECIMAL,
    max_traffic  INT
);

-- Product traffic - sharded for write performance (write-heavy)
-- Shards 0-9 distribute writes across multiple partitions
CREATE TABLE IF NOT EXISTS product_traffic (
    id           UUID,
    shard_id     INT,         -- 0-9, distributes high-traffic writes
    curr_traffic INT,
    PRIMARY KEY ((id, shard_id))
);

-- Secondary indexes for common lookup patterns
CREATE INDEX IF NOT EXISTS product_ean_idx      ON product (ean_code);
CREATE INDEX IF NOT EXISTS product_category_idx ON product (category);

-- ------------------------------------------------------------
-- Traffic events  (time-series, TTL = 24 h)
-- Partitioned by (product_id, hour_bucket) for even distribution
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS traffic_events (
    product_id   UUID,
    hour_bucket  TIMESTAMP,   -- truncated to the hour
    event_time   TIMESTAMP,
    visitor_id   UUID,
    event_type   TEXT,        -- 'page_view' | 'cart_add' | 'checkout'
    page_views   INT,
    PRIMARY KEY ((product_id, hour_bucket), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC)
  AND default_time_to_live = 86400;

-- ------------------------------------------------------------
-- Price history  (full audit trail, newest-first per product)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices (
    product_id   UUID,
    effective_at TIMESTAMP,
    base_price   DECIMAL,
    multiplier   FLOAT,
    final_price  DECIMAL,
    PRIMARY KEY (product_id, effective_at)
) WITH CLUSTERING ORDER BY (effective_at DESC);
