"""
Database layer for ScyllaDB.

Uses prepared statements for performance and sharded writes for horizontal scaling.
Traffic counters are spread across 10 shards per product to avoid hot partitions.
"""

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy, RetryPolicy
from cassandra.query import ConsistencyLevel
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import logging
import os

logger = logging.getLogger(__name__)

# ── Sharding config ──────────────────────────────────────────────────────────
TRAFFIC_SHARDS = 10  # Number of shards for distributed writes (0-9)

# Config from environment, with sensible defaults
SCYLLA_HOSTS = os.getenv("SCYLLA_HOSTS", "127.0.0.1").split(",")
SCYLLA_USER  = os.getenv("SCYLLA_USER",  "cassandra")
SCYLLA_PASS  = os.getenv("SCYLLA_PASS",  "cassandra")
SCYLLA_DC    = os.getenv("SCYLLA_DC",    "datacenter1")
KEYSPACE     = "pricing"

# Initialize connection
auth_provider = PlainTextAuthProvider(username=SCYLLA_USER, password=SCYLLA_PASS)

cluster = Cluster(
    SCYLLA_HOSTS,
    auth_provider=auth_provider,
    load_balancing_policy=DCAwareRoundRobinPolicy(local_dc=SCYLLA_DC),
    default_retry_policy=RetryPolicy(),
    protocol_version=4,
    connect_timeout=10,
)

session = cluster.connect(KEYSPACE)
session.default_consistency_level = ConsistencyLevel.LOCAL_ONE

logger.info("Connected to ScyllaDB: %s", SCYLLA_HOSTS)

# Prepared statements
# (These are compiled once at startup for better performance)─────────────

_INSERT_PRODUCT = session.prepare("""
    INSERT INTO product
        (id, ean_code, sku_name, seller_name, description,
         category, cur_price, max_traffic)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""")

_GET_PRODUCT = session.prepare("""
    SELECT id, ean_code, sku_name, seller_name, description,
           category, cur_price, max_traffic
    FROM product WHERE id = ?
""")

_UPDATE_PRODUCT_PRICE = session.prepare("""
    UPDATE product
    SET cur_price = ?
    WHERE id = ?
""")

_UPDATE_TRAFFIC_SHARD = session.prepare("""
    UPDATE product_traffic
    SET curr_traffic = ?
    WHERE id = ? AND shard_id = ?
""")

_GET_TRAFFIC_SHARD = session.prepare("""
    SELECT curr_traffic FROM product_traffic
    WHERE id = ? AND shard_id = ?
""")

_UPDATE_PRODUCT_FIELDS = session.prepare("""
    UPDATE product
    SET ean_code = ?, sku_name = ?, seller_name = ?, description = ?,
        category = ?, cur_price = ?, max_traffic = ?
    WHERE id = ?
""")

_LIST_PRODUCTS = session.prepare("""
    SELECT id, ean_code, sku_name, seller_name, description,
           category, cur_price, max_traffic
    FROM product
""")

_INSERT_EVENT = session.prepare("""
    INSERT INTO traffic_events
        (product_id, hour_bucket, event_time, visitor_id, event_type, page_views)
    VALUES (?, ?, ?, ?, ?, ?)
""")

_INSERT_PRICE = session.prepare("""
    INSERT INTO prices (product_id, effective_at, base_price, multiplier, final_price)
    VALUES (?, ?, ?, ?, ?)
""")

_GET_LATEST_PRICE = session.prepare("""
    SELECT base_price, multiplier, final_price, effective_at
    FROM prices WHERE product_id = ? ORDER BY effective_at DESC LIMIT 1
""")

_GET_PRICE_HISTORY = session.prepare("""
    SELECT product_id, effective_at, base_price, multiplier, final_price
    FROM prices WHERE product_id = ? ORDER BY effective_at DESC LIMIT ?
""")

# ── Database API ────────────────────────────────────────────────────────────

def upsert_product(p) -> None:
    session.execute(_INSERT_PRODUCT, (
        p.id, p.ean_code, p.sku_name, p.seller_name,
        p.description, p.category, p.cur_price,
        p.max_traffic,
    ))
    # Initialize all traffic shards to 0
    for shard in range(TRAFFIC_SHARDS):
        session.execute(_UPDATE_TRAFFIC_SHARD, (0, p.id, shard))


def get_product(product_id):
    """Get product metadata. Aggregates traffic from primary shard only (fast path)."""
    row = session.execute(_GET_PRODUCT, (product_id,)).one()
    if not row:
        return None
    # For efficiency, read traffic from the primary shard only
    # In a multi-node cluster, you'd aggregate from all shards if accuracy is critical
    primary_shard = _select_traffic_shard(product_id)
    traffic_row = session.execute(_GET_TRAFFIC_SHARD, (product_id, primary_shard)).one()
    curr_traffic = traffic_row.curr_traffic if traffic_row else 0
    
    # Return a row-like object with curr_traffic included
    from collections import namedtuple
    ProductRow = namedtuple('ProductRow', list(row._fields) + ['curr_traffic'])
    return ProductRow(*list(row), curr_traffic)


def list_products():
    """List all products with traffic aggregated from primary shard."""
    from collections import namedtuple
    products = session.execute(_LIST_PRODUCTS)
    results = []
    for row in products:
        # Get traffic from primary shard
        primary_shard = _select_traffic_shard(row.id)
        traffic_row = session.execute(_GET_TRAFFIC_SHARD, (row.id, primary_shard)).one()
        curr_traffic = traffic_row.curr_traffic if traffic_row else 0
        
        ProductRow = namedtuple('ProductRow', list(row._fields) + ['curr_traffic'])
        results.append(ProductRow(*list(row), curr_traffic))
    return results


def update_product_fields(product_id, update):
    """Partial update. Fetches current values for missing fields."""
    row = get_product(product_id)
    if not row:
        return None
    
    # Use provided value or fall back to existing
    session.execute(_UPDATE_PRODUCT_FIELDS, (
        update.ean_code     or row.ean_code,
        update.sku_name     or row.sku_name,
        update.seller_name  or row.seller_name,
        update.description  or row.description,
        update.category     or row.category,
        update.cur_price    if update.cur_price    is not None else row.cur_price,
        update.max_traffic  if update.max_traffic  is not None else row.max_traffic,
        product_id,
    ))
    return get_product(product_id)


def _select_traffic_shard(product_id: UUID) -> int:
    """Which shard for this product. Hash-based, deterministic."""
    return hash(str(product_id)) % TRAFFIC_SHARDS


def _get_total_traffic(product_id: UUID) -> int:
    """Sum all traffic shards (for accuracy on multi-node clusters)."""
    total = 0
    for shard in range(TRAFFIC_SHARDS):
        row = session.execute(_GET_TRAFFIC_SHARD, (product_id, shard)).one()
        if row and row.curr_traffic:
            total += row.curr_traffic
    return total


def update_traffic_and_price(product_id: UUID, curr_traffic: int, cur_price) -> None:
    """Update traffic (to a sharded write) and price (in main table)."""
    # Consistently route to same shard for this product
    shard = _select_traffic_shard(product_id)
    session.execute(_UPDATE_TRAFFIC_SHARD, (curr_traffic, product_id, shard))
    session.execute(_UPDATE_PRODUCT_PRICE, (cur_price, product_id))


def record_traffic_event(product_id, visitor_id, event_type: str, page_views: int) -> None:
    now         = datetime.now(timezone.utc)
    hour_bucket = now.replace(minute=0, second=0, microsecond=0)
    session.execute(_INSERT_EVENT, (
        product_id, hour_bucket, now, visitor_id, event_type, page_views
    ))


def record_price(product_id, base_price: float, multiplier: float, final_price: float) -> None:
    """Store a price snapshot for audit trail."""
    session.execute(_INSERT_PRICE, (
        product_id,
        datetime.now(timezone.utc),
        base_price,
        multiplier,
        final_price,
    ))


def get_latest_price(product_id):
    return session.execute(_GET_LATEST_PRICE, (product_id,)).one()


def get_price_history(product_id, limit: int = 50):
    return list(session.execute(_GET_PRICE_HISTORY, (product_id, limit)))
