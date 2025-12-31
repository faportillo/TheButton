# The Button

A backend-focused implementation of a global "button game" inspired by Reddit's _The Button_. This project demonstrates clean event-driven architecture using Kafka, PostgreSQL, Redis, and FastAPI—with a pure domain core for game logic.

## Overview

The Button implements a **single global button** shared by all users worldwide. When users press the button:

1. The API accepts press events and produces them to Kafka
2. A reducer service consumes events, applies game rules, and updates global state
3. State changes are persisted to PostgreSQL (source of truth)
4. Redis pub/sub notifies connected clients via Server-Sent Events (SSE)

The project exists to practice **good backend code design**: clear separation between API, reducer, shared domain, and infrastructure layers—with particular emphasis on Kafka consumer patterns, manual offset management, and a pure domain core free of framework dependencies.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───▶│  FastAPI    │───▶│    Kafka    │───▶│   Reducer   │
│             │    │    API      │    │   Topic     │    │   Service   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       ▲                                                        │
       │                                                        ▼
       │           ┌─────────────┐                      ┌─────────────┐
       └───────────│    Redis    │◀─────────────────────│  PostgreSQL │
         (SSE)     │   Pub/Sub   │    (notify after     │  (append-   │
                   └─────────────┘     DB write)        │  only log)  │
                                                        └─────────────┘
```

### Data Flow

1. **HTTP Press** → Client calls `POST /v1/events/press`
2. **Kafka Produce** → API generates `request_id`, produces message to `press_button` topic
3. **Kafka Consume** → Reducer polls messages in batches
4. **Apply Rules** → Pure `apply_batch()` function computes new `GlobalState` from events
5. **DB Write** → New state snapshot appended to `global_states` table
6. **Redis Notify** → Reducer publishes to `state_updates:v1` channel
7. **Kafka Commit** → Offsets committed **only after** successful DB write
8. **SSE Push** → API streams updates to connected clients

### Key Invariants

- **DB before Kafka commit**: Offsets are never committed until the state is persisted
- **Redis as invalidation only**: Pub/sub is best-effort; PostgreSQL is the source of truth
- **Pure domain logic**: The rules engine has no dependencies on FastAPI, SQLAlchemy, or Kafka

## Game Mechanics

The button responds to collective user activity through a dynamic rules engine. Game rules are stored as JSON in the `rulesets` table and loaded by the reducer at startup.

**The specific mechanics are intentionally undocumented**—discovering how the button behaves is part of the game.

## Tech Stack

| Component       | Technology                     |
| --------------- | ------------------------------ |
| Language        | Python 3.13                    |
| API Framework   | FastAPI                        |
| Message Broker  | Apache Kafka (confluent-kafka) |
| Database        | PostgreSQL 16                  |
| Cache/Pub-Sub   | Redis 7                        |
| ORM             | SQLAlchemy 2.0                 |
| Settings        | Pydantic Settings              |
| SSE             | sse-starlette                  |
| Package Manager | Poetry                         |
| Containers      | Docker Compose                 |

## Project Structure

```
src/
├── api/                    # FastAPI application
│   ├── __init__.py
│   ├── config.py           # APISettings (Pydantic BaseSettings)
│   ├── contracts.py        # Message schemas for inter-service communication
│   ├── health.py           # Health check utilities (Redis, Kafka, DB)
│   ├── kafka.py            # Kafka producer wrapper
│   ├── redis.py            # Redis connection and pub/sub listener
│   ├── routes.py           # FastAPI app and route handlers
│   ├── schemas.py          # API response models (Pydantic)
│   └── state.py            # Database queries for global state
│
├── reducer/                # Kafka consumer service
│   ├── __init__.py
│   ├── config.py           # ReducerSettings (Pydantic BaseSettings)
│   ├── consumer.py         # Kafka consumer wrapper
│   ├── main.py             # Consumer loop with backoff/retry
│   ├── notify.py           # Redis publisher for state updates
│   ├── updater.py          # apply_event / apply_batch (pure functions)
│   ├── writer.py           # Database write operations
│   └── rules/
│       ├── logic.py        # Pure game logic (the secret sauce)
│       └── retriever.py    # Load rulesets from database
│
├── shared/                 # Shared domain layer
│   ├── __init__.py
│   ├── constants.py        # Kafka topics, Redis channels, consumer group
│   └── models.py           # Domain entities + SQLAlchemy ORM models
│
├── error.py                # (Reserved for custom exceptions)
└── logger.py               # (Reserved for logging configuration)

tests/
├── api/
│   ├── conftest.py         # API test fixtures
│   ├── contract/           # Message contract tests
│   ├── integration/        # Redis, Kafka, state integration tests
│   └── unit/               # Unit tests for routes, kafka, redis, health
│
└── reducer/
    ├── conftest.py         # Reducer test fixtures
    ├── integration/        # Writer, retriever SQLite integration tests
    └── unit/               # Unit tests for consumer, logic, updater, notify
```

## Configuration

### Environment Variables

Copy `example.env` to `.env` and configure:

```bash
cp example.env .env
```

#### Required Variables

| Variable           | Description                  | Example                                                     |
| ------------------ | ---------------------------- | ----------------------------------------------------------- |
| `DATABASE_URL`     | PostgreSQL connection string | `postgresql://thebutton:thebutton@localhost:5432/thebutton` |
| `KAFKA_BROKER_URL` | Kafka bootstrap servers      | `localhost:9092`                                            |
| `REDIS_HOST`       | Redis hostname               | `localhost`                                                 |
| `REDIS_PORT`       | Redis port                   | `6379`                                                      |

#### Environment Mode

| Variable      | Values         | Description              |
| ------------- | -------------- | ------------------------ |
| `API_ENV`     | `dev` / `prod` | API environment mode     |
| `REDUCER_ENV` | `dev` / `prod` | Reducer environment mode |

In `prod` mode, Kafka credentials are required:

- `KAFKA_API_KEY`
- `KAFKA_API_SECRET`

#### Reducer Backoff Settings

| Variable                       | Default | Description              |
| ------------------------------ | ------- | ------------------------ |
| `REDUCER_BACKOFF_MAX_ATTEMPTS` | 3       | Max retries before crash |
| `REDUCER_BACKOFF_BASE_SECONDS` | 1.0     | Initial backoff delay    |
| `REDUCER_MAX_BACKOFF_SECONDS`  | 30.0    | Maximum backoff delay    |

### Constants

Defined in `src/shared/constants.py`:

| Constant                                                                | Value              | Description                  |
| ----------------------------------------------------------------------- | ------------------ | ---------------------------- |
| `API_KAFKA_TOPIC` / `REDUCER_KAFKA_TOPIC`                               | `press_button`     | Kafka topic for press events |
| `API_REDIS_STATE_UPDATE_CHANNEL` / `REDUCER_REDIS_STATE_UPDATE_CHANNEL` | `state_updates:v1` | Redis pub/sub channel        |
| `REDUCER_KAFKA_GROUP_ID`                                                | `group.reducer`    | Consumer group ID            |
| `REDUCER_KAFKA_CONSUMER_BATCH_SIZE`                                     | 100                | Max messages per poll        |

## Running Locally

### Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/docs/#installation)
- Docker & Docker Compose

### Quick Start

The fastest way to get everything running:

```bash
# 1. Install dependencies
poetry install

# 2. Set up environment file
make setup-env

# 3. Start infrastructure (PostgreSQL, Redis, Kafka)
make start

# 4. In separate terminals, start the services:
make run-api      # Terminal 1: API server
make run-reducer  # Terminal 2: Reducer service
```

The API will be available at `http://localhost:8000`.

### Detailed Setup

#### 1. Start Infrastructure

```bash
# Start PostgreSQL, Redis, and Kafka
make start

# Or manually:
docker compose up -d postgres redis kafka

# Or start with admin UIs (Kafka UI, Redis Commander, pgAdmin)
make docker-up-all
```

Verify services are healthy:

```bash
make docker-health
```

#### 2. Install Dependencies

```bash
# Configure Poetry to use in-project virtualenv (optional)
poetry config virtualenvs.in-project true

# Install all dependencies
poetry install
```

#### 3. Configure Environment

```bash
# Create .env from example
make setup-env

# Or manually
cp example.env .env
```

Edit `.env` if needed (defaults should work for local development).

#### 4. Run Database Migrations

```bash
# Run migrations (creates tables)
poetry run alembic upgrade head
```

#### 5. Start the API

```bash
# Using Makefile
make run-api

# Or manually
poetry run uvicorn api.routes:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. You can verify it's running:

```bash
curl http://localhost:8000/health
```

#### 6. Start the Reducer

In a separate terminal:

```bash
# Using Makefile
make run-reducer

# Or manually
poetry run python -m reducer.main
```

The reducer will connect to Kafka and begin consuming press events. You should see log messages indicating it's ready.

### Running Everything in Docker

Alternatively, you can run the entire stack in Docker:

```bash
# Start everything (infrastructure + API + reducer)
make start-full

# View logs
make logs-apps

# Stop everything
make stop
```

### Verifying the Setup

1. **Check API health**: `curl http://localhost:8000/health`
2. **Check current state**: `curl http://localhost:8000/v1/states/current`
3. **Test button press**: See [Testing the Streaming Endpoint](#testing-the-streaming-endpoint) below

## API Endpoints

### Press the Button

```http
POST /v1/events/press
```

**Response** (202 Accepted):

```json
{
  "request_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "timestamp_ms": 1704067200000
}
```

**Errors**:

- `503 Service Unavailable`: Kafka unavailable or buffer full

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
```

Returns a `text/event-stream` with real-time state updates:

```
event: state_update
data: {"id": 43, "counter": 12346, ...}

event: state_update
data: {"id": 44, "counter": 12347, ...}
```

See [Testing the Streaming Endpoint](#testing-the-streaming-endpoint) below for how to test this endpoint.

### Health Checks

| Endpoint            | Purpose              | Checks                 |
| ------------------- | -------------------- | ---------------------- |
| `GET /health`       | Load balancer health | Redis, Kafka, Database |
| `GET /health/live`  | Kubernetes liveness  | Service running        |
| `GET /health/ready` | Kubernetes readiness | Redis, Kafka           |

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run only unit tests (fast)
make test-unit

# Run integration tests (requires Docker)
make test-integration

# Run with coverage
make test-coverage

# Run specific test file
make test-file FILE="tests/reducer/unit/test_logic.py"

# Run tests matching pattern
make test-match PATTERN="health"
```

See `make help` for all available test targets.

### Testing the Streaming Endpoint

The `/v1/states/stream` endpoint uses Server-Sent Events (SSE) and cannot be tested directly in Swagger. Here are three ways to test it:

#### Option 1: Python Script (Recommended)

A simple Python script is provided for command-line testing:

```bash
# Basic usage (defaults to http://localhost:8000)
python test_stream.py

# Custom URL
python test_stream.py --url http://localhost:8000

# Custom timeout
python test_stream.py --timeout 120
```

The script will connect to the stream and print state updates as they arrive in real-time.

#### Option 2: HTML Test Page

Open `test_stream.html` in your web browser. This provides a visual interface with:

- Connection controls (connect/disconnect)
- Real-time display of state updates
- Formatted JSON output
- Status indicators

Simply open the file in your browser, enter the API URL (default: `http://localhost:8000`), and click "Connect".

#### Option 3: curl Command

For quick testing from the command line:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:8000/v1/states/stream
```

The `-N` flag disables buffering so you see events in real-time.

#### Testing the Full Flow

To see state updates in the stream:

1. **Start the stream** using one of the methods above
2. **Trigger state updates** by pressing the button (in another terminal):

   ```bash
   # First, get a challenge
   curl -X POST http://localhost:8000/v1/challenge
   
   # Then press the button (requires solving PoW or set POW_BYPASS=true in .env)
   curl -X POST http://localhost:8000/v1/events/press \
     -H "Content-Type: application/json" \
     -d '{
       "challenge_id": "...",
       "difficulty": 4,
       "expires_at": ...,
       "signature": "...",
       "nonce": "..."
     }'
   ```

3. **Watch the stream** receive state updates as the reducer processes button presses

> **Note**: For development/testing, you can set `POW_BYPASS=true` in your `.env` file to skip proof-of-work verification.

## Design Notes

### Manual Kafka Offset Management

The reducer uses `enable.auto.commit = False` and commits offsets only after successful database writes:

```python
# In reducer main loop
new_state = apply_batch(state, events, rules_config, rules_hash)
persisted_global_state = write_state(new_state)  # DB write first
consumer.commit(asynchronous=False)              # Then commit offsets
```

This ensures no message is "lost" if the reducer crashes after consuming but before persisting.

### Pure Domain Core

The rules engine (`reducer/rules/logic.py`) and state updater (`reducer/updater.py`) are pure Python functions with no framework dependencies:

```python
def apply_event(
    state: GlobalStateEntity,
    event: PressEvent,
    rules_config: RulesConfig,
    rules_hash: str,
) -> CreateGlobalStateEntity:
    # Pure logic: no I/O, no side effects
```

This makes the core game logic easy to test in isolation and reason about.

### Redis as Invalidation Layer

Redis pub/sub is treated as best-effort notification:

```python
try:
    publish_state_update(redis, persisted_global_state)
except:
    logger.warning("Redis publish failed — continuing without blocking reducer")
```

Clients always read the latest state from PostgreSQL. Redis just tells them _when_ to fetch.

### Error Handling & Backoff

The reducer implements exponential backoff with a crash-after-max-attempts pattern:

```python
if backoff_attempt >= settings.backoff_max_attempts:
    logger.critical("Reducer reached max attempts — crashing")
    raise  # Let orchestration restart the container

delay = min(max_backoff, base_seconds * (2 ** backoff_attempt))
time.sleep(delay)
```

## Docker Services

| Service           | Port | Description                            |
| ----------------- | ---- | -------------------------------------- |
| `postgres`        | 5432 | PostgreSQL 16 database                 |
| `redis`           | 6379 | Redis 7 for pub/sub                    |
| `kafka`           | 9092 | Kafka (KRaft mode, no ZooKeeper)       |
| `kafka-ui`        | 8080 | Kafka UI (optional, `--profile tools`) |
| `redis-commander` | 8081 | Redis Commander (optional)             |
| `pgadmin`         | 8082 | pgAdmin (optional)                     |

```bash
# Start core services
docker compose up -d postgres redis kafka

# Start with admin UIs
docker compose --profile tools up -d

# View logs
docker compose logs -f kafka

# Stop all
docker compose --profile tools down

# Clean up (remove volumes)
docker compose --profile tools down -v
```

## Future Enhancements

- [ ] Alembic migrations for database schema management
- [ ] Dead Letter Queue (DLQ) for poison messages
- [ ] Multi-partition Kafka scaling for higher throughput
- [ ] Rate limiting on the API layer
- [ ] Metrics and observability (Prometheus, Grafana)
- [ ] WebSocket support as alternative to SSE
- [ ] Frontend client for the button game
- [ ] Richer rulesets with time-based events and special conditions

## License

MIT
