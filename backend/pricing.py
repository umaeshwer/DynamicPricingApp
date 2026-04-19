"""
pricing.py — Dynamic pricing multiplier engine.

Strategy
--------
Each product carries its own `max_traffic` ceiling, so surge thresholds
are relative to that product's expected demand — a niche SKU and a
bestseller each have independent scaling curves.

Multiplier curve
----------------
  traffic_ratio = curr_traffic / max_traffic   (clamped 0 → 1)

  0.00 – 0.30  →  discount zone  : multiplier slides from MIN (0.85) up to 1.0
  0.30 – 0.70  →  neutral zone   : multiplier stays near 1.0  (±2%)
  0.70 – 1.00  →  surge zone     : multiplier climbs from 1.0 up to MAX (2.0)

Event-type weight
-----------------
Not all traffic signals carry equal weight:
  page_view  → weight 1.0
  cart_add   → weight 2.5   (high purchase intent)
  checkout   → weight 4.0   (strongest signal)

The weighted page-view count is passed into the multiplier calc
so checkout spikes drive faster price increases.
"""

from dataclasses import dataclass

# ── Tuneable constants ───────────────────────────────────────────────────────
MIN_MULTIPLIER   = 0.85   # maximum discount during very low traffic
MAX_MULTIPLIER   = 2.00   # hard ceiling on price surge
NEUTRAL_LOW      = 0.30   # ratio below which discounting begins
NEUTRAL_HIGH     = 0.70   # ratio above which surging begins

EVENT_WEIGHTS = {
    "page_view": 1.0,
    "cart_add":  2.5,
    "checkout":  4.0,
}


@dataclass
class PricingResult:
    base_price:   float
    multiplier:   float
    final_price:  float
    traffic_ratio: float
    zone:         str     # 'discount' | 'neutral' | 'surge'


def _zone(ratio: float) -> str:
    if ratio < NEUTRAL_LOW:
        return "discount"
    if ratio <= NEUTRAL_HIGH:
        return "neutral"
    return "surge"


def compute_multiplier(curr_traffic: int, max_traffic: int) -> tuple[float, float]:
    """
    Returns (multiplier, traffic_ratio).
    All arithmetic is kept simple and auditable.
    """
    if max_traffic <= 0:
        return 1.0, 0.0

    ratio = min(1.0, max(0.0, curr_traffic / max_traffic))

    if ratio < NEUTRAL_LOW:
        # Linear interpolation from MIN_MULTIPLIER → 1.0
        t = ratio / NEUTRAL_LOW
        multiplier = MIN_MULTIPLIER + t * (1.0 - MIN_MULTIPLIER)

    elif ratio <= NEUTRAL_HIGH:
        # Flat neutral band
        multiplier = 1.0

    else:
        # Linear interpolation from 1.0 → MAX_MULTIPLIER
        t = (ratio - NEUTRAL_HIGH) / (1.0 - NEUTRAL_HIGH)
        multiplier = 1.0 + t * (MAX_MULTIPLIER - 1.0)

    return round(multiplier, 4), round(ratio, 4)


def weighted_traffic(curr_traffic: int, event_type: str) -> int:
    """
    Applies event-type weight so checkout events drive faster surges
    than passive page views.
    """
    weight = EVENT_WEIGHTS.get(event_type, 1.0)
    return int(curr_traffic * weight)


def get_dynamic_price(
    base_price:   float,
    curr_traffic: int,
    max_traffic:  int,
    event_type:   str = "page_view",
) -> PricingResult:
    """
    Computes dynamic price based on traffic ratio.
    
    Note: curr_traffic should already have weights applied to the increment.
    See main.py where weighted_page_views are added to curr_traffic.
    """
    multiplier, ratio = compute_multiplier(curr_traffic, max_traffic)
    final = round(base_price * multiplier, 2)
    return PricingResult(
        base_price=base_price,
        multiplier=multiplier,
        final_price=final,
        traffic_ratio=ratio,
        zone=_zone(ratio),
    )
