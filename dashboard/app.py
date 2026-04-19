"""
app.py — Streamlit dashboard for the Dynamic Pricing Monitor.

Sections
--------
1. Sidebar    — product selector, traffic simulator
2. KPI row    — live metrics (price, multiplier, traffic, zone)
3. Price chart — multiplier trend from price history
4. Product table — all products with live prices
5. Raw event log — last N traffic events (auto-refresh)
"""

import os
import time
from datetime import datetime
from uuid import uuid4

import pandas as pd
import requests
import streamlit as st

# ── Config ───────────────────────────────────────────────────────────────────
API_URL       = os.getenv("API_URL", "http://api:8000")  # Use Docker service name by default
REFRESH_SECS  = 5
HISTORY_LIMIT = 100

st.set_page_config(
    page_title="Dynamic Pricing Monitor",
    page_icon="📈",
    layout="wide",
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def api_get(path: str):
    try:
        r = requests.get(f"{API_URL}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error [{path}]: {e}")
        return None


def api_post(path: str, payload: dict):
    try:
        r = requests.post(f"{API_URL}{path}", json=payload, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error [{path}]: {e}")
        return None


def zone_badge(zone: str) -> str:
    icons = {"discount": "🟢 Discount", "neutral": "🟡 Neutral", "surge": "🔴 Surge"}
    return icons.get(zone, zone)


# ── Page header ───────────────────────────────────────────────────────────────
st.title("📈 Dynamic Pricing Monitor")
st.caption(f"Auto-refreshes every {REFRESH_SECS}s · Powered by FastAPI + ScyllaDB")

# ── Fetch all products ────────────────────────────────────────────────────────
products = api_get("/products") or []
product_map = {p["sku_name"]: p for p in products}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("� Admin")
    
    st.subheader("➕ Register New Product")
    with st.form("new_product"):
        sku_name    = st.text_input("SKU name")
        ean_code    = st.text_input("EAN code")
        seller_name = st.text_input("Seller name")
        category    = st.text_input("Category")
        description = st.text_area("Description")
        base_price  = st.number_input("Base price ($)", min_value=0.01, value=29.99, step=0.01)
        max_traffic = st.number_input("Max traffic ceiling", min_value=1, value=1000, step=100)
        submitted   = st.form_submit_button("Register")

    if submitted and sku_name:
        payload = {
            "id":          str(uuid4()),
            "sku_name":    sku_name,
            "ean_code":    ean_code,
            "seller_name": seller_name,
            "category":    category,
            "description": description,
            "cur_price":   base_price,
            "max_traffic": max_traffic,
            "curr_traffic": 0,
        }
        result = api_post("/products", payload)
        if result:
            st.success(f"Registered: {result['sku_name']} (id: {result['id']})")
            st.rerun()


# ── Product selector (main content area) ───────────────────────────────────────
if not products:
    st.info("Register a product in the sidebar to get started.")
    st.stop()

selected_name = st.selectbox("Select Product", list(product_map.keys()))

# ── Main content ──────────────────────────────────────────────────────────────
if selected_name:
    selected = product_map[selected_name]
    pid      = selected["id"]

    price_data = api_get(f"/price/{pid}")
    history    = api_get(f"/price/{pid}/history?limit={HISTORY_LIMIT}") or []

    # KPI row
    st.subheader(f"📦 {selected_name}")
    c1, c2, c3, c4, c5 = st.columns(5)

    if price_data:
        traffic_pct = round(price_data["curr_traffic"] / max(price_data["max_traffic"], 1) * 100, 1)
        c1.metric("Current price",    f"${price_data['final_price']:.2f}")
        c2.metric("Base price",       f"${price_data['base_price']:.2f}")
        c3.metric("Multiplier",       f"{price_data['multiplier']:.4f}×")
        c4.metric("Traffic",          f"{price_data['curr_traffic']} / {price_data['max_traffic']}",
                  delta=f"{traffic_pct}% capacity")
        c5.metric("EAN",              price_data["ean_code"])
    else:
        st.warning("No price data yet — send a traffic event first.")

    # Multiplier trend chart
    if history:
        df = pd.DataFrame(history)
        df["effective_at"] = pd.to_datetime(df["effective_at"])
        df = df.sort_values("effective_at")
        st.subheader("Multiplier trend")
        st.line_chart(df.set_index("effective_at")[["multiplier", "final_price"]])

    # Traffic simulation buttons
    st.divider()
    st.subheader("🚦 Simulate Traffic")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("👁️ Page View", use_container_width=True):
            result = api_post("/traffic-event", {
                "product_id": pid,
                "visitor_id": str(uuid4()),
                "event_type": "page_view",
                "page_views": 1,
            })
            if result:
                st.success(
                    f"**New price:** ${result['final_price']:.2f}  \n"
                    f"Multiplier: **{result['multiplier']:.4f}×**  \n"
                    f"Traffic: **{result['curr_traffic']}** / {result['max_traffic']}"
                )
                st.rerun()
    
    with col2:
        if st.button("🛒 Add to Cart", use_container_width=True):
            result = api_post("/traffic-event", {
                "product_id": pid,
                "visitor_id": str(uuid4()),
                "event_type": "cart_add",
                "page_views": 1,
            })
            if result:
                st.success(
                    f"**New price:** ${result['final_price']:.2f}  \n"
                    f"Multiplier: **{result['multiplier']:.4f}×**  \n"
                    f"Traffic: **{result['curr_traffic']}** / {result['max_traffic']}"
                )
                st.rerun()
    
    with col3:
        if st.button("💳 Checkout", use_container_width=True):
            result = api_post("/traffic-event", {
                "product_id": pid,
                "visitor_id": str(uuid4()),
                "event_type": "checkout",
                "page_views": 1,
            })
            if result:
                st.success(
                    f"**New price:** ${result['final_price']:.2f}  \n"
                    f"Multiplier: **{result['multiplier']:.4f}×**  \n"
                    f"Traffic: **{result['curr_traffic']}** / {result['max_traffic']}"
                )
                st.rerun()

st.divider()

# All products table
st.subheader("🗂 All Products — Live Prices")
rows = []
for p in products:
    pr = api_get(f"/price/{p['id']}")
    rows.append({
        "SKU":          p["sku_name"],
        "EAN":          p["ean_code"],
        "Seller":       p["seller_name"],
        "Category":     p["category"],
        "Base ($)":     float(p["cur_price"]),
        "Live ($)":     pr["final_price"] if pr else "—",
        "Multiplier":   f"{pr['multiplier']:.4f}×" if pr else "—",
        "Traffic":      f"{p['curr_traffic']} / {p['max_traffic']}",
    })

if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

# Auto-refresh
time.sleep(REFRESH_SECS)
st.rerun()
