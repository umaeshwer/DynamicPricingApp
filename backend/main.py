"""
FastAPI backend for dynamic pricing engine.

Handles product management and real-time pricing updates based on traffic signals.
Writes are sharded for horizontal scaling on high-traffic products.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import db
import pricing as engine
from models import (
    HealthResponse,
    PriceHistory,
    PriceResponse,
    Product,
    ProductUpdate,
    TrafficEvent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Cleanup on shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    yield
    logger.info("Closing DB connection")
    db.cluster.shutdown()


app = FastAPI(
    title="Dynamic Pricing API",
    description="Adjusts product prices in real-time based on web traffic signals stored in ScyllaDB.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/products", response_model=Product, status_code=201, tags=["Products"])
async def create_product(product: Product):
    """Create a new product. max_traffic is used to calibrate the pricing multiplier."""
    db.upsert_product(product)
    # Insert initial price record with 1.0x multiplier (neutral zone)
    db.record_price(
        product.id,
        base_price=float(product.cur_price),
        multiplier=1.0,
        final_price=float(product.cur_price)
    )
    logger.info("Product created: %s (%s)", product.id, product.sku_name)
    return product


@app.get("/products", response_model=List[Product], tags=["Products"])
async def list_products():
    """Get all products."""
    rows = db.list_products()
    return [Product(**row._asdict()) for row in rows]


@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
async def get_product(product_id: UUID):
    """Get a product by ID."""
    row = db.get_product(product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**row._asdict())


@app.patch("/products/{product_id}", response_model=Product, tags=["Products"])
async def update_product(product_id: UUID, update: ProductUpdate):
    """Update product fields."""
    row = db.update_product_fields(product_id, update)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**row._asdict())


@app.post("/traffic-event", response_model=PriceResponse, tags=["Pricing"])
async def record_traffic_event(event: TrafficEvent):
    """Record a traffic event and recompute pricing.
    
    Different event types (page_view, cart_add, checkout) have different weights
    to reflect purchase intent. Updates are sharded for write performance.
    """
    row = db.get_product(event.product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    # Weight the page_views increment based on event type, then add to current traffic
    weighted_page_views = engine.weighted_traffic(event.page_views, event.event_type)
    new_traffic = (row.curr_traffic or 0) + weighted_page_views

    result = engine.get_dynamic_price(
        base_price=float(row.cur_price),
        curr_traffic=new_traffic,
        max_traffic=row.max_traffic,
        event_type=event.event_type,
    )

    db.record_traffic_event(
        event.product_id, event.visitor_id, event.event_type, event.page_views
    )
    db.update_traffic_and_price(event.product_id, new_traffic, result.final_price)
    db.record_price(event.product_id, result.base_price, result.multiplier, result.final_price)

    logger.info(
        "Traffic event [%s] product=%s traffic=%d mult=%.4f price=%.2f zone=%s",
        event.event_type, event.product_id, new_traffic,
        result.multiplier, result.final_price, result.zone,
    )

    return PriceResponse(
        product_id=event.product_id,
        sku_name=row.sku_name,
        ean_code=row.ean_code,
        category=row.category,
        base_price=result.base_price,
        multiplier=result.multiplier,
        final_price=result.final_price,
        curr_traffic=new_traffic,
        max_traffic=row.max_traffic,
        updated_at=datetime.now(timezone.utc),
    )


@app.get("/price/{product_id}", response_model=PriceResponse, tags=["Pricing"])
async def get_current_price(product_id: UUID):
    """Get the current price of a product."""
    row = db.get_product(product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    price_row = db.get_latest_price(product_id)
    
    # If no price history exists, return the current product price with 1.0x multiplier
    if not price_row:
        return PriceResponse(
            product_id=product_id,
            sku_name=row.sku_name,
            ean_code=row.ean_code,
            category=row.category,
            base_price=float(row.cur_price),
            multiplier=1.0,
            final_price=float(row.cur_price),
            curr_traffic=row.curr_traffic or 0,
            max_traffic=row.max_traffic,
            updated_at=datetime.now(timezone.utc),
        )

    return PriceResponse(
        product_id=product_id,
        sku_name=row.sku_name,
        ean_code=row.ean_code,
        category=row.category,
        base_price=float(price_row.base_price),
        multiplier=price_row.multiplier,
        final_price=float(price_row.final_price),
        curr_traffic=row.curr_traffic or 0,
        max_traffic=row.max_traffic,
        updated_at=price_row.effective_at,
    )


@app.get("/price/{product_id}/history", response_model=List[PriceHistory], tags=["Pricing"])
async def get_price_history(
    product_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Get price history for a product."""
    rows = db.get_price_history(product_id, limit)
    if not rows:
        raise HTTPException(status_code=404, detail="No price history found")
    return [
        PriceHistory(
            product_id=r.product_id,
            effective_at=r.effective_at,
            base_price=float(r.base_price),
            multiplier=r.multiplier,
            final_price=float(r.final_price),
        )
        for r in rows
    ]


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Ops"])
async def health():
    """Ping ScyllaDB and return overall service health."""
    try:
        db.session.execute("SELECT release_version FROM system.local")
        scylla_status = "ok"
    except Exception as exc:
        logger.error("ScyllaDB health check failed: %s", exc)
        scylla_status = f"error: {exc}"
    return HealthResponse(status="ok", scylla=scylla_status)
