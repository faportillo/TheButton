# The Button

A full-stack implementation of a global "button game" inspired by Reddit's _The Button_. This project demonstrates event-driven architecture with real-time updates, featuring a modern web frontend and a robust backend built with Kafka, PostgreSQL, Redis, and FastAPI.

## 🎮 Overview

**The Button** is a collaborative web game where users worldwide share a single global button. When pressed, the button's behavior changes dynamically based on collective user activity, creating an emergent gameplay experience driven by real-time interactions.

### How It Works

1. **User presses the button** → Frontend solves a proof-of-work challenge and sends the press event
2. **API accepts the event** → Validates proof-of-work, applies rate limiting, and produces to Kafka
3. **Reducer processes events** → Consumes from Kafka in batches, applies game rules, and updates global state
4. **State persisted** → New state snapshot saved to PostgreSQL (source of truth)
5. **Watcher monitors cooldowns** → Periodically checks if phases should transition down when no activity occurs
6. **Real-time notifications** → Redis pub/sub broadcasts state changes
7. **Clients updated** → Frontend receives updates via Server-Sent Events (SSE)

The game features dynamic phases (CALM → WARM → HOT → CHAOS) that respond to user activity patterns. The watcher service ensures phases automatically transition down when activity decreases, creating an engaging collaborative experience.

## 🏗️ Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Browser   │───▶│  FastAPI    │───▶│    Kafka    │───▶│   Reducer   │
│  Frontend   │    │    API      │    │   Topic     │    │   Service   │
│  (Port 3000)│    │ (Port 8000) │    │  (Port 9092)│    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       ▲                                                        │
       │                                                        ▼
       │           ┌─────────────┐                      ┌─────────────┐
       └───────────│    Redis    │◀─────────────────────│  PostgreSQL │
         (SSE)     │   Pub/Sub   │    (notify after     │  (Port 5432)│
                   │  (Port 6379)│     DB write)        │             │
                   └─────────────┘                      └─────────────┘
                                                               ▲
                                                               │
                                                    ┌─────────────┐
                                                    │   Watcher   │
                                                    │   Service   │
                                                    │  (Periodic) │
                                                    └─────────────┘
```

### Key Design Principles

- **Event-Driven**: All button presses flow through Kafka for scalability and reliability
- **Pure Domain Logic**: Game rules are framework-agnostic and easily testable
- **Manual Offset Management**: Kafka offsets committed only after successful database writes
- **Redis as Notification Layer**: Pub/sub is best-effort; PostgreSQL is the source of truth
- **Real-Time Updates**: Server-Sent Events (SSE) for live state synchronization

## ✨ Features

### Frontend

- **Interactive UI**: Clean, responsive interface with visual phase indicators
- **Real-Time Updates**: Live state synchronization via Server-Sent Events
- **Proof-of-Work**: Client-side computation to prevent spam
- **Visual Feedback**: Dynamic background colors and animations based on game phase
- **Error Handling**: Graceful degradation and user-friendly error messages

### Backend

- **Rate Limiting**: Per-IP rate limiting to prevent abuse
- **Proof-of-Work Verification**: Cryptographic challenge-response system
- **Health Checks**: Comprehensive health endpoints for monitoring
- **Batch Processing**: Efficient Kafka consumer with configurable batch sizes
- **Automatic Phase Transitions**: Watcher service monitors cooldowns and transitions phases down when activity decreases
- **Database Migrations**: Alembic for schema management
- **Comprehensive Testing**: Unit, integration, and E2E test suites

## 🛠️ Tech Stack

| Component           | Technology                      |
| ------------------- | ------------------------------- |
| **Frontend**        | Vanilla JavaScript (ES Modules) |
| **Backend**         | Python 3.13                     |
| **API Framework**   | FastAPI                         |
| **Message Broker**  | Apache Kafka (confluent-kafka)  |
| **Database**        | PostgreSQL 16                   |
| **Cache/Pub-Sub**   | Redis 7                         |
| **ORM**             | SQLAlchemy 2.0                  |
| **Settings**        | Pydantic Settings               |
| **SSE**             | sse-starlette                   |
| **Package Manager** | Poetry                          |
| **Containers**      | Docker Compose                  |
| **Reverse Proxy**   | Nginx                           |

## 🚀 Quick Start

### Prerequisites

- **Python 3.13**
- **[Poetry](https://python-poetry.org/docs/#installation)** (Python package manager)
- **Docker & Docker Compose**
- **Make** (for convenience commands)

### One-Command Setup

The fastest way to get everything running:

```bash
# Install dependencies and start infrastructure
make setup
make start-backend

# In separate terminals:
make run-api      # Terminal 1: API server
make run-reducer  # Terminal 2: Reducer service
make start-frontend  # Terminal 3: Frontend server
```

Then open your browser to:

- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Docker Setup (Recommended)

Run everything in Docker for a complete isolated environment:

```bash
# Start full stack (infrastructure + services)
make start-full
```

This starts:

- PostgreSQL, Redis, Kafka
- API server (port 8000)
- Reducer service
- Watcher service (periodic phase transition checker)
- Nginx reverse proxy (port 8080)

Access the application at:

- **Nginx (with frontend)**: http://localhost:8080
- **API directly**: http://localhost:8000
- **Health check**: http://localhost:8000/health

### Detailed Setup

#### 1. Install Dependencies

```bash
make setup
# Or manually:
cd backend && poetry install
```

#### 2. Configure Environment

```bash
cd backend
cp example.env .env
# Edit .env if needed (defaults work for local development)
```

#### 3. Start Infrastructure

```bash
make start-backend
# This starts PostgreSQL, Redis, and Kafka
# Runs database migrations automatically
```

#### 4. Start Services

**Option A: Run locally (for development)**

```bash
# Terminal 1: API
make run-api

# Terminal 2: Reducer
make run-reducer

# Terminal 3: Watcher (optional, included in Docker)
make run-watcher

# Terminal 4: Frontend
make start-frontend
```

**Option B: Run in Docker (for production-like environment)**

```bash
make start-full
```

## 📁 Project Structure

```
TheButton/
├── frontend/              # Frontend application
│   ├── index.html        # Main HTML page
│   ├── main.js           # Application logic
│   ├── pow.js            # Proof-of-work solver
│   └── styles.css        # Styling
│
├── backend/               # Backend application
│   ├── src/
│   │   ├── api/          # FastAPI application
│   │   │   ├── routes.py      # API endpoints
│   │   │   ├── config.py      # API settings
│   │   │   ├── pow.py         # Proof-of-work verification
│   │   │   ├── ratelimiter.py # Rate limiting
│   │   │   └── ...
│   │   │
│   │   ├── reducer/      # Kafka consumer service
│   │   │   ├── main.py        # Consumer loop
│   │   │   ├── consumer.py    # Kafka consumer wrapper
│   │   │   ├── updater.py     # State update logic
│   │   │   ├── writer.py      # Database operations
│   │   │   └── rules/         # Game rules engine
│   │   │
│   │   ├── watcher/      # Phase transition watcher
│   │   │   ├── main.py        # Watcher scheduler
│   │   │   ├── watcher_lambda.py  # Phase transition logic
│   │   │   └── config.py      # Watcher settings
│   │   │
│   │   └── shared/       # Shared domain layer
│   │       ├── models.py      # Domain entities & ORM
│   │       ├── constants.py   # Constants
│   │       ├── kafka.py        # Kafka utilities
│   │       ├── rules.py        # Rules retriever
│   │       └── state.py        # State access
│   │
│   ├── tests/            # Test suite
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── Makefile
│
└── Makefile              # Root Makefile (orchestrates everything)
```

## 📡 API Endpoints

### Press the Button

```http
POST /v1/events/press
Content-Type: application/json

{
  "challenge_id": "...",
  "difficulty": 4,
  "expires_at": 1704067200000,
  "signature": "...",
  "nonce": "12345"
}
```

**Response** (202 Accepted):

```json
{
  "request_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "timestamp_ms": 1704067200000
}
```

### Get Proof-of-Work Challenge

```http
GET /v1/challenge
```

**Response** (200 OK):

```json
{
  "challenge_id": "...",
  "difficulty": 4,
  "expires_at": 1704067200000,
  "signature": "..."
}
```

### Get Current State

```http
GET /v1/states/current
```

**Response** (200 OK):

```json
{
  "id": 42,
  "last_applied_offset": 1000,
  "counter": 12345,
  "phase": 2,
  "entropy": 0.65,
  "reveal_until_ms": 1704067500000,
  "cooldown_ms": 2000,
  "updated_at_ms": 1704067200000,
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Stream State Updates (SSE)

```http
GET /v1/states/stream
Accept: text/event-stream
```

Returns real-time state updates via Server-Sent Events:

```
event: state_update
data: {"id": 43, "counter": 12346, "phase": 2, ...}

event: state_update
data: {"id": 44, "counter": 12347, "phase": 3, ...}
```

### Health Checks

| Endpoint            | Purpose              | Checks                 |
| ------------------- | -------------------- | ---------------------- |
| `GET /health`       | Load balancer health | Redis, Kafka, Database |
| `GET /health/live`  | Kubernetes liveness  | Service running        |
| `GET /health/ready` | Kubernetes readiness | Redis, Kafka           |

## 🎮 Game Mechanics

The button responds to collective user activity through a dynamic rules engine. Game rules are stored as JSON in the database and loaded by the reducer at startup.

**Key Concepts:**

- **Phases**: CALM (0) → WARM (1) → HOT (2) → CHAOS (3)
- **Entropy**: Measures activity intensity (0.0 to 1.0), increases with rapid presses and decays over time
- **Cooldown**: Time between allowed presses (varies by phase)
- **Reveal Window**: Time period when button is active
- **Automatic Phase Transitions**: The watcher service monitors cooldowns and automatically transitions phases down when activity decreases

**Phase Transition Logic:**

- Phases transition **up** when entropy increases (via button presses)
- Phases transition **down** automatically when:
  - No button presses occur for the phase's cooldown period
  - The watcher service detects expired cooldowns and sends transition events
  - The reducer processes these events and recalculates phase based on current entropy

The specific mechanics are intentionally undocumented—discovering how the button behaves is part of the game experience!

## 🧪 Testing

### Run All Tests

```bash
make test
```

### Test Categories

```bash
make test-unit          # Fast unit tests
make test-integration   # Integration tests (requires Docker)
make test-e2e          # End-to-end tests (requires full stack)
make test-coverage     # Tests with coverage report
```

### E2E Test Setup

E2E tests require the full stack to be running:

```bash
# Option 1: Docker
make start-full
make test-e2e

# Option 2: Local
make start-backend
make run-api  # In separate terminal
make test-e2e
```

## 🛠️ Development

### Available Make Commands

Run `make help` to see all available commands:

```bash
make help               # Show all commands
make setup             # Install all dependencies
make start             # Start backend + frontend locally
make start-backend     # Start only backend infrastructure
make start-frontend    # Start frontend dev server
make start-full        # Start everything in Docker
make stop              # Stop all services
make status            # Show service status
make logs              # View logs (use SERVICE=api to filter)
make run-api           # Run API locally
make run-reducer       # Run reducer locally
make run-watcher       # Run watcher locally
make test              # Run all tests
make clean             # Clean cache and build artifacts
```

### Backend-Specific Commands

```bash
cd backend
make help              # See backend-specific commands
make db-upgrade        # Run database migrations
make db-migrate        # Create new migration
make format            # Format code with black
make lint              # Run linter checks
```

### Environment Variables

Key environment variables (see `backend/example.env` for full list):

| Variable                   | Description                        | Default            |
| -------------------------- | ---------------------------------- | ------------------ |
| `DATABASE_URL`             | PostgreSQL connection string       | `postgresql://...` |
| `KAFKA_BROKER_URL`         | Kafka bootstrap servers            | `localhost:9092`   |
| `REDIS_HOST`               | Redis hostname                     | `localhost`        |
| `REDIS_PORT`               | Redis port                         | `6379`             |
| `API_ENV`                  | API environment (`dev`/`prod`)     | `dev`              |
| `WATCHER_ENV`              | Watcher environment (`dev`/`prod`) | `dev`              |
| `WATCHER_INTERVAL_SECONDS` | Watcher check interval in seconds  | `30`               |
| `POW_BYPASS`               | Skip PoW verification (dev)        | `false`            |
| `RATE_LIMIT_BYPASS`        | Skip rate limiting (dev)           | `false`            |

## 🐳 Docker Services

| Service           | Port | Description                            |
| ----------------- | ---- | -------------------------------------- |
| `postgres`        | 5432 | PostgreSQL 16 database                 |
| `redis`           | 6379 | Redis 7 for pub/sub                    |
| `kafka`           | 9092 | Kafka (KRaft mode, no ZooKeeper)       |
| `api`             | 8000 | FastAPI application                    |
| `reducer`         | -    | Kafka consumer service                 |
| `watcher`         | -    | Periodic phase transition watcher      |
| `nginx`           | 8080 | Reverse proxy (optional)               |
| `kafka-ui`        | 8080 | Kafka UI (optional, `--profile tools`) |
| `redis-commander` | 8081 | Redis Commander (optional)             |
| `pgadmin`         | 8082 | pgAdmin (optional)                     |

### Start with Admin UIs

```bash
cd backend
docker compose --profile tools up -d
```

## 📊 Monitoring & Debugging

### View Logs

```bash
make logs                    # All services
make logs SERVICE=api        # Specific service
cd backend && make logs      # Backend services
```

### Check Service Status

```bash
make status
```

### Health Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

## 🔧 Configuration

### Database Migrations

```bash
cd backend
make db-upgrade      # Apply migrations
make db-migrate      # Create new migration (use MSG="description")
make db-downgrade    # Rollback last migration
```

### Seed Rules

```bash
cd backend
make db-seed-rules   # Load initial rules from config/rules.json
```

## 👁️ Watcher Service

The watcher service is a background process that monitors the global state and automatically triggers phase transitions when activity decreases. This ensures the game doesn't get "stuck" in high-intensity phases when users stop pressing the button.

### How It Works

1. **Periodic Checks**: The watcher runs on a configurable interval (default: 30 seconds)
2. **Cooldown Monitoring**: Checks if the current phase's cooldown period has expired
3. **Phase-Specific Logic**:
   - **CHAOS (3)**: Transitions down when `cooldown_chaos_ms` expires
   - **HOT (2)**: Transitions down when `cooldown_chaos_ms` expires
   - **WARM (1)**: Transitions down when `cooldown_warm_ms` expires
   - **CALM (0)**: No transition needed (already at lowest phase)
4. **Event Generation**: Sends a phase transition message to Kafka when cooldown expires
5. **Reducer Processing**: The reducer processes the transition event and recalculates phase based on current entropy

### Configuration

The watcher can be configured via environment variables:

```bash
WATCHER_ENV=dev                    # Environment (dev/prod)
WATCHER_INTERVAL_SECONDS=30        # Check interval in seconds
DATABASE_URL=postgresql://...      # Database connection
KAFKA_BROKER_URL=localhost:9092   # Kafka broker
```

### Running the Watcher

**Docker (recommended):**

```bash
make start-full  # Watcher starts automatically
```

**Local development:**

```bash
make run-watcher  # Run watcher locally
```

**View logs:**

```bash
docker compose logs -f watcher
# Or locally, logs appear in the terminal
```

### Consistency Guarantees

The watcher ensures consistency by:

- Using the same rules version (`ruleshash`) that was used to compute the current state
- Preventing race conditions when rules are updated
- Working independently of the reducer without cross-dependencies

## 🎯 Design Highlights

### Manual Kafka Offset Management

Offsets are committed only after successful database writes, ensuring no message loss:

```python
new_state = apply_batch(state, events, rules_config, rules_hash)
persisted_global_state = write_state(new_state)  # DB write first
consumer.commit(asynchronous=False)              # Then commit offsets
```

### Pure Domain Core

Game logic is framework-agnostic and easily testable:

```python
def apply_event(
    state: GlobalStateEntity,
    event: PressEvent,
    rules_config: RulesConfig,
    rules_hash: str,
) -> CreateGlobalStateEntity:
    # Pure logic: no I/O, no side effects
```

### Redis as Notification Layer

Redis pub/sub is best-effort; PostgreSQL is always the source of truth:

```python
try:
    publish_state_update(redis, persisted_global_state)
except:
    logger.warning("Redis publish failed — continuing without blocking reducer")
```

## 🚧 Future Enhancements

- [ ] WebSocket support as alternative to SSE
- [ ] Multi-partition Kafka scaling for higher throughput
- [ ] Dead Letter Queue (DLQ) for poison messages
- [ ] Metrics and observability (Prometheus, Grafana)
- [ ] Richer rulesets with time-based events
- [ ] User authentication and leaderboards
- [ ] Mobile app support

## 📝 License

MIT

## 🤝 Contributing

This is a personal project for learning and experimentation. Feel free to fork and adapt for your own use!

---

**Enjoy pressing the button!** 🎮
