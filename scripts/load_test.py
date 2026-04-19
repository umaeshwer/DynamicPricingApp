"""
load_test.py — Simulate bursty traffic against the pricing API.

Usage:
    python scripts/load_test.py --rps 50 --duration 30
"""

import argparse
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import requests

API_URL     = "http://localhost:8000"
EVENT_TYPES = ["page_view", "page_view", "page_view", "cart_add", "checkout"]  # weighted


def get_product_ids():
    r = requests.get(f"{API_URL}/products", timeout=5)
    r.raise_for_status()
    return [p["id"] for p in r.json()]


def send_event(product_ids):
    payload = {
        "product_id": random.choice(product_ids),
        "visitor_id": str(uuid4()),
        "event_type": random.choice(EVENT_TYPES),
        "page_views": random.randint(1, 5),
    }
    try:
        r = requests.post(f"{API_URL}/traffic-event", json=payload, timeout=3)
        return r.status_code, r.json().get("multiplier") if r.ok else None
    except Exception as e:
        return 0, str(e)


def run(rps: int, duration: int):
    print(f"Fetching product IDs from {API_URL}...")
    product_ids = get_product_ids()
    if not product_ids:
        print("No products found. Run scripts/seed.py first.")
        return

    print(f"Running load test: {rps} req/s for {duration}s against {len(product_ids)} products")
    interval  = 1.0 / rps
    end_time  = time.time() + duration
    results   = {"ok": 0, "err": 0}
    lock      = threading.Lock()

    def worker():
        status, mult = send_event(product_ids)
        with lock:
            if status == 200:
                results["ok"] += 1
                if results["ok"] % 100 == 0:
                    print(f"  {results['ok']} ok | last multiplier={mult:.4f}")
            else:
                results["err"] += 1

    # Use ThreadPoolExecutor for proper thread management
    with ThreadPoolExecutor(max_workers=min(rps, 100)) as executor:
        futures = []
        while time.time() < end_time:
            futures.append(executor.submit(worker))
            time.sleep(interval)
        
        # Wait for all pending tasks to complete
        for future in futures:
            try:
                future.result(timeout=10)
            except Exception as e:
                with lock:
                    results["err"] += 1
                print(f"Worker error: {e}")

    print(f"\nDone — {results['ok']} ok / {results['err']} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rps",      type=int, default=20,  help="Requests per second")
    parser.add_argument("--duration", type=int, default=30,  help="Test duration in seconds")
    args = parser.parse_args()
    run(args.rps, args.duration)
