from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from api.schemas import (
    GlobalState,
    PressResponse,
    PressRequest,
    ChallengeResponse,
    ErrorResponse,
)
import uuid
import time
from api.kafka import create_producer, send_message, flush_producer, KafkaException
import shared.constants as constants
from shared.models import PersistedGlobalState
import logging
from api.state import get_latest_state, get_state_by_id, SessionLocal
from api.redis import create_redis_connection, listen_on_pubsub
from api.health import (
    check_redis_health,
    check_kafka_health,
    check_database_health,
    aggregate_health,
)
from api.ratelimiter import rate_limit_request, rate_limit_press, get_real_ip
from api.pow import generate_challenge, verify_solution, Solution
import json
from datetime import datetime


logger = logging.getLogger(__name__)

app = FastAPI(
    title="The Button API",
    description="API for The Button game",
    version="1.0.0",
)

producer = create_producer()
redis_client = create_redis_connection()


# =============================================================================
# Rate Limit Dependencies
# =============================================================================


def require_rate_limit(request: Request) -> str:
    """Dependency that enforces general rate limiting. Returns client IP."""
    return rate_limit_request(request, redis_client)


def require_press_rate_limit(request: Request) -> str:
    """Dependency that enforces stricter rate limiting for press endpoint."""
    return rate_limit_press(request, redis_client)


# =============================================================================
# Challenge & Event Endpoints
# =============================================================================


@app.post(
    "/v1/challenge",
    response_model=ChallengeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get a PoW challenge",
    description="Request a proof-of-work challenge. Solve it by finding a nonce where SHA256(challenge_id + ':' + nonce) starts with 'difficulty' zeros.",
)
def get_challenge(client_ip: str = Depends(require_rate_limit)):
    """
    Issue a proof-of-work challenge.
    
    Client must solve by finding a nonce such that:
    SHA256(challenge_id + ":" + nonce) starts with `difficulty` hex zeros.
    
    Example (difficulty=4):
    - challenge_id = "abc123"
    - Find nonce where SHA256("abc123:NONCE").hexdigest() starts with "0000"
    """
    challenge = generate_challenge()
    logger.debug(f"Issued challenge {challenge.challenge_id} to {client_ip}")
    return ChallengeResponse(**challenge.to_dict())


@app.post(
    "/v1/events/press",
    response_model=PressResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid PoW solution"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Kafka unavailable"},
    },
    summary="Press the button",
    description="Submit a button press with a valid proof-of-work solution.",
)
def press_button(
    body: PressRequest,
    client_ip: str = Depends(require_press_rate_limit),
):
    # Verify proof-of-work solution
    solution = Solution(
        challenge_id=body.challenge_id,
        difficulty=body.difficulty,
        expires_at=body.expires_at,
        signature=body.signature,
        nonce=body.nonce,
    )
    
    is_valid, error = verify_solution(redis_client, solution)
    if not is_valid:
        logger.warning(f"Invalid PoW from {client_ip}: {error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Invalid proof of work",
        )
    
    # PoW valid - process the button press
    req_id = uuid.uuid4().hex
    timestamp_ms = int(time.time() * 1000)
    payload = {"timestamp_ms": timestamp_ms, "request_id": req_id}
    logger.debug(f"Press request {req_id} from {client_ip} (valid PoW)")
    
    try:
        send_message(producer, value=payload, key=constants.API_KAFKA_GLOBAL_KEY)
        remaining = flush_producer(producer)
        if remaining > 0:
            logger.error(
                f"Failed to flush message {req_id}, {remaining} still in queue"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Message delivery timed out",
            )
    except BufferError:
        logger.error(f"Producer buffer full, dropping message {req_id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily overloaded",
        )
    except KafkaException as e:
        logger.error(f"Kafka error for message {req_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Message broker unavailable",
        )

    return PressResponse(request_id=req_id, timestamp_ms=timestamp_ms)


@app.get(
    "/v1/states/current",
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
def get_current_state(_: str = Depends(require_rate_limit)):
    try:
        # Get latest state
        state = get_latest_state()
        return GlobalState(**state)

    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No state found",
        )


@app.get(
    "/v1/states/stream",
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def stream_state(request: Request, _: str = Depends(require_rate_limit)):
    async def event_generator():
        try:
            async for update in listen_on_pubsub(redis_client):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("Client disconnected from SSE stream")
                    break
                if isinstance(update, PersistedGlobalState):
                    state = get_state_by_id(update.id)
                    yield f"event: state_update\ndata: {json.dumps(state)}\n\n"
                else:
                    logger.warning(f"Unexpected update type: {type(update)}")
                    continue

        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': 'Stream interrupted'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if behind nginx
        },
    )


# =============================================================================
# Health Check Endpoints
# =============================================================================


@app.get(
    "/health",
    tags=["Health"],
    summary="Overall health check",
    description="Returns health status of all dependencies. Use for load balancer health checks.",
)
def health_check():
    """
    Comprehensive health check for all dependencies.

    Returns:
        - 200: All systems healthy
        - 503: One or more systems unhealthy
    """
    checks = {
        "redis": check_redis_health(redis_client),
        "kafka": check_kafka_health(producer),
        "database": check_database_health(SessionLocal),
    }

    overall_status, checks_dict = aggregate_health(checks)

    response = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks_dict,
    }

    status_code = 200 if overall_status == "healthy" else 503

    return JSONResponse(content=response, status_code=status_code)


@app.get(
    "/health/live",
    tags=["Health"],
    summary="Liveness probe",
    description="Kubernetes liveness probe. Returns 200 if the service is running.",
)
def liveness_probe():
    """
    Simple liveness check - just confirms the service is running.

    This should NOT check external dependencies to avoid cascading failures.
    If this fails, Kubernetes will restart the pod.
    """
    return {"status": "alive"}


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Readiness probe",
    description="Kubernetes readiness probe. Returns 200 if ready to accept traffic.",
)
def readiness_probe():
    """
    Readiness check - confirms the service can handle requests.

    Checks critical dependencies (Kafka for producing, Redis for streaming).
    If this fails, Kubernetes will stop routing traffic to this pod.
    """
    checks = {
        "redis": check_redis_health(redis_client),
        "kafka": check_kafka_health(producer),
    }

    overall_status, checks_dict = aggregate_health(checks)

    response = {
        "status": overall_status,
        "checks": checks_dict,
    }

    if overall_status == "healthy":
        return JSONResponse(content=response, status_code=200)
    else:
        return JSONResponse(content=response, status_code=503)
