"""
Dynamic pricing engine.

Adjusts prices based on real-time traffic.
- Low traffic (0-30%): discount zone
- Medium traffic (30-70%): neutral, stay near base price
- High traffic (70%+): surge zone

Event types have different weights (checkout = strongest signal).
"""

from dataclasses import dataclass

# Tunable constants
MIN_MULTIPLIER   = 0.85
MAX_MULTIPLIER   = 2.00
NEUTRAL_LOW      = 0.30   # Below this = discount
NEUTRAL_HIGH     = 0.70   # Above this = surge

EVENT_WEIGHTS = {
    "page_view": 1.0,
    "cart_add":  2.5,      # Higher intent
    "checkout":  4.0,      # Highest intent
}


@dataclass
class PricingResult:
    base_price:   float
    multiplier:   float
    final_price:  float
    traffic_ratio: float
    zone:         str     # 'discount' | 'neutral' | 'surge'


def _zone(ratio: float) -> str:
    """Which pricing zone are we in?"""
    if ratio < NEUTRAL_LOW:
        return "discount"
    if ratio <= NEUTRAL_HIGH:
        return "neutral"
    return "surge"


def compute_multiplier(curr_traffic: int, max_traffic: int) -> tuple[float, float]:
    """Calculate (multiplier, ratio) from traffic."""
    if max_traffic <= 0:
        return 1.0, 0.0

    ratio = min(1.0, max(0.0, curr_traffic / max_traffic))

    if ratio < NEUTRAL_LOW:
        # Discount zone: slide from MIN_MULTIPLIER to 1.0
        t = ratio / NEUTRAL_LOW
        multiplier = MIN_MULTIPLIER + t * (1.0 - MIN_MULTIPLIER)
    elif ratio <= NEUTRAL_HIGH:
        # Neutral zone: hold at 1.0
        multiplier = 1.0
    else:
        # Surge zone: climb from 1.0 to MAX_MULTIPLIER
        t = (ratio - NEUTRAL_HIGH) / (1.0 - NEUTRAL_HIGH)
        multiplier = 1.0 + t * (MAX_MULTIPLIER - 1.0)

    return round(multiplier, 4), round(ratio, 4)


def weighted_traffic(curr_traffic: int, event_type: str) -> int:
    """Apply event weight. Checkout events spike faster than page views."""
    weight = EVENT_WEIGHTS.get(event_type, 1.0)
    return int(curr_traffic * weight)


def get_dynamic_price(
    base_price:   float,
    curr_traffic: int,
    max_traffic:  int,
    event_type:   str = "page_view",
) -> PricingResult:
    """Compute the dynamic price."""
    multiplier, ratio = compute_multiplier(curr_traffic, max_traffic)
    final = round(base_price * multiplier, 2)
    return PricingResult(
        base_price=base_price,
        multiplier=multiplier,
        final_price=final,
        traffic_ratio=ratio,
        zone=_zone(ratio),
    )
