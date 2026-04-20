"""
Populate the database with sample products.

Usage:
  python scripts/seed.py
"""

import requests
from uuid import uuid4

API_URL = "http://localhost:8000"

SAMPLE_PRODUCTS = [
    {
        "id":          str(uuid4()),
        "sku_name":    "iPhone 17",
        "ean_code":    "5901234123457",
        "seller_name": "Acme Corp",
        "category":    "SaaS",
        "description": "Monthly pro plan with unlimited access",
        "cur_price":   29.99,
        "max_traffic": 2000,
        "curr_traffic": 0,
    },
    {
        "id":          str(uuid4()),
        "sku_name":    "GoPro Hero 11",
        "ean_code":    "5901234123458",
        "seller_name": "Acme Corp",
        "category":    "SaaS",
        "description": "5-seat team plan with admin dashboard",
        "cur_price":   99.00,
        "max_traffic": 1500,
        "curr_traffic": 0,
    },
    {
        "id":          str(uuid4()),
        "sku_name":    "Rayban Smart Glasses",
        "ean_code":    "5901234123459",
        "seller_name": "Acme Corp",
        "category":    "SaaS",
        "description": "SSO, audit logs, SLA 99.99%",
        "cur_price":   249.00,
        "max_traffic": 500,
        "curr_traffic": 0,
    },
    {
        "id":          str(uuid4()),
        "sku_name":    "Razr Laptop 2024",
        "ean_code":    "5901234123460",
        "seller_name": "Acme Corp",
        "category":    "Add-ons",
        "description": "1 million API call credits",
        "cur_price":   19.99,
        "max_traffic": 3000,
        "curr_traffic": 0,
    },
    {
        "id":          str(uuid4()),
        "sku_name":    "Sony WH-1000XM5",
        "ean_code":    "5901234123461",
        "seller_name": "Acme Corp",
        "category":    "Add-ons",
        "description": "1TB additional cloud storage",
        "cur_price":   14.99,
        "max_traffic": 1000,
        "curr_traffic": 0,
    },
]


def seed():
    print(f"Seeding {len(SAMPLE_PRODUCTS)} products to {API_URL}...")
    for product in SAMPLE_PRODUCTS:
        r = requests.post(f"{API_URL}/products", json=product)
        if r.ok:
            print(f"  ✓ {product['sku_name']} ({product['id']})")
        else:
            print(f"  ✗ {product['sku_name']} — {r.status_code}: {r.text}")
    print("Done.")


if __name__ == "__main__":
    seed()
