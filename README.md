# Dynamic Pricing Engine

Real-time price adjustments based on live traffic. Built with FastAPI, ScyllaDB, and Streamlit.

## How It Works

When users interact with products, traffic signals flow into the system, which adjusts prices in real-time:

```
User interactions  →  FastAPI  →  ScyllaDB  →  Dashboard
(page views,           (computes    (stores       (live
 cart adds,             prices)     events)      monitoring)
checkouts)
```

## Files

```
.
├── backend/           # FastAPI server
│  ├── main.py
│  ├── db.py          # Database layer (sharded writes)
│  ├── pricing.py     # Multiplier math
│  └── models.py
├── dashboard/        # Streamlit UI
├── scripts/          # Utilities
│  ├── seed.py
│  └── load_test.py
├── schema.cql        # ScyllaDB setup
└── docker-compose.yml
```

## Quick Start

**With Docker:**

```bash
# Start everything
docker compose up --build

# In another terminal, seed sample products
python scripts/seed.py

# Open dashboard
open http://localhost:8501
```

**Without Docker:**

```bash
# Start ScyllaDB
docker run -d --name scylla -p 9042:9042 scylladb/scylla \
  --smp 1 --memory 750M --overprovisioned 1

# Wait 30s for ScyllaDB to start, then
cqlsh 127.0.0.1 -f schema.cql

# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Dashboard (new terminal)
streamlit run dashboard/app.py

# Seed data
python scripts/seed.py
```

## API Endpoints

| Method | Path | What It Does |
|--------|------|-------------|
| POST | `/products` | Create a product |
| GET | `/products` | List all products |
| GET | `/products/{id}` | Get one product |
| PATCH | `/products/{id}` | Update a product |
| POST | `/traffic-event` | Record traffic + recalc price |
| GET | `/price/{id}` | Get current price |
| GET | `/price/{id}/history` | Price history |
| GET | `/health` | Health check |

API docs available at `http://localhost:8000/docs`

## Pricing

Prices adjust based on traffic volume relative to a product's `max_traffic` ceiling:

- **Low traffic (0–30%)**: discount zone, prices drop (0.85x–1.0x)
- **Medium traffic (30–70%)**: neutral zone, prices stay near base (1.0x)
- **High traffic (70%+)**: surge zone, prices climb (1.0x–2.0x)

Different event types have different weights:
- `page_view`: 1.0x (baseline)
- `cart_add`: 2.5x (buyer signal)
- `checkout`: 4.0x (strongest signal)

So one checkout event has 4× more impact than a page view on pricing.

## Database Optimization

Product traffic updates are **sharded** across 10 partitions per product to avoid write bottlenecks on hot items. This lets the system handle thousands of traffic events per second per product.

## Config

Set via environment variables:

| Variable | Default | Purpose |
|----------|---------|----------|
| `SCYLLA_HOSTS` | `127.0.0.1` | ScyllaDB hosts (comma-separated) |
| `SCYLLA_USER` | `cassandra` | Username |
| `SCYLLA_PASS` | `cassandra` | Password |
| `SCYLLA_DC` | `datacenter1` | Datacenter name |
| `API_URL` | `http://api:8000` | Backend URL (for dashboard) |

## Testing

```bash
# Simulate traffic
python scripts/load_test.py --rps 20 --duration 60
```
