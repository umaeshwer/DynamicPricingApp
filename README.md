# Dynamic Pricing Application

Real-time pricing engine that adjusts product prices proportionally to web traffic, built with **FastAPI**, **ScyllaDB**, and **Streamlit**.

## Architecture

```
Frontend App
     │  POST /traffic-event
     ▼
FastAPI (backend/)
     │  reads/writes via prepared statements
     ▼
ScyllaDB  ──── tables: product, traffic_events, prices
     ▲
     │  reads live prices
Streamlit Dashboard (dashboard/)
```

## Project Structure

```
dynamic-pricing/
├── schema.cql                # ScyllaDB keyspace + tables
├── requirements.txt
├── docker-compose.yml        # ScyllaDB + API + Dashboard
├── Dockerfile.api
├── Dockerfile.dashboard
├── backend/
│   ├── main.py               # FastAPI routes
│   ├── db.py                 # ScyllaDB session + prepared statements
│   ├── pricing.py            # Multiplier engine
│   └── models.py             # Pydantic schemas
├── dashboard/
│   └── app.py                # Streamlit monitor
└── scripts/
    ├── seed.py               # Populate sample products
    └── load_test.py          # Simulate bursty traffic
```

## Quickstart (Docker)

```bash
# 1. Start everything
docker compose up --build

# 2. Seed sample products (wait ~20s for ScyllaDB to be ready)
python scripts/seed.py

# 3. Open the dashboard
open http://localhost:8501

# 4. API docs
open http://localhost:8000/docs
```

## Quickstart (Local)

```bash
# 1. Start ScyllaDB
docker run -d --name scylla -p 9042:9042 scylladb/scylla \
  --smp 1 --memory 750M --overprovisioned 1

# 2. Wait ~30s then apply schema
cqlsh 127.0.0.1 -f schema.cql

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start FastAPI
uvicorn backend.main:app --reload --port 8000

# 5. Start Streamlit (new terminal)
streamlit run dashboard/app.py

# 6. Seed products
python scripts/seed.py
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/products` | Register a new product |
| GET | `/products` | List all products |
| GET | `/products/{id}` | Get a single product |
| PATCH | `/products/{id}` | Update product fields |
| POST | `/traffic-event` | Record traffic + recompute price |
| GET | `/price/{id}` | Get current price |
| GET | `/price/{id}/history` | Price history (last N records) |
| GET | `/health` | Health check |

## Pricing Logic

Each product has a `max_traffic` ceiling. The multiplier is computed as:

```
traffic_ratio = curr_traffic / max_traffic

ratio 0.00–0.30  →  discount zone   (0.85× → 1.00×)
ratio 0.30–0.70  →  neutral zone    (1.00×)
ratio 0.70–1.00  →  surge zone      (1.00× → 2.00×)
```

Event-type weights (cart_add and checkout events accelerate surges):
- `page_view`  → 1.0×
- `cart_add`   → 2.5×
- `checkout`   → 4.0×

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCYLLA_HOSTS` | `127.0.0.1` | Comma-separated ScyllaDB hosts |
| `SCYLLA_USER` | `cassandra` | ScyllaDB username |
| `SCYLLA_PASS` | `cassandra` | ScyllaDB password |
| `SCYLLA_DC` | `datacenter1` | Local datacenter name |

## Load Testing

```bash
# 20 requests/sec for 60 seconds
python scripts/load_test.py --rps 20 --duration 60
```
