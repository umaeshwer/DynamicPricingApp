from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from decimal import Decimal
from datetime import datetime
from typing import Optional


class Product(BaseModel):
    id:           UUID    = Field(default_factory=uuid4)
    ean_code:     str
    sku_name:     str
    seller_name:  str
    description:  str
    category:     str
    cur_price:    Decimal
    max_traffic:  int               # upper traffic ceiling — used as 100% in multiplier calc
    curr_traffic: int = 0           # live visitor count

    model_config = {"from_attributes": True}


class ProductUpdate(BaseModel):
    ean_code:     Optional[str]     = None
    sku_name:     Optional[str]     = None
    seller_name:  Optional[str]     = None
    description:  Optional[str]     = None
    category:     Optional[str]     = None
    cur_price:    Optional[Decimal] = None
    max_traffic:  Optional[int]     = None


class TrafficEvent(BaseModel):
    product_id:  UUID
    visitor_id:  UUID = Field(default_factory=uuid4)
    event_type:  str  = "page_view"   # page_view | cart_add | checkout
    page_views:  int  = 1


class PriceResponse(BaseModel):
    product_id:   UUID
    sku_name:     str
    ean_code:     str
    category:     str
    base_price:   float
    multiplier:   float
    final_price:  float
    curr_traffic: int
    max_traffic:  int
    updated_at:   datetime


class PriceHistory(BaseModel):
    product_id:   UUID
    effective_at: datetime
    base_price:   float
    multiplier:   float
    final_price:  float


class HealthResponse(BaseModel):
    status:  str
    scylla:  str
    version: str = "1.0.0"
