from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse, StreamingResponse
from api.schemas import GlobalState, PressResponse, ErrorResponse
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


@app.post(
    "/v1/events/press",
    response_model=PressResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        503: {"model": ErrorResponse, "description": "Kafka unavailable"},
    },
)
def press_button():
    req_id = uuid.uuid4().hex
    timestamp_ms = int(time.time() * 1000)
    payload = {"timestamp_ms": timestamp_ms, "request_id": req_id}
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


@app.get("/v1/states/current")
def get_current_state():
    try:
        # Get latest state
        state = get_latest_state()
        return GlobalState(**state)

    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No state found",
        )


@app.get("/v1/states/stream")
async def stream_state(request: Request):
    async def event_generator():
        try:
            async for update in listen_on_pubsub():
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("Client disconnected from SSE stream")
                    break
                if type(update) == PersistedGlobalState:
                    state = get_state_by_id(update.id)
                    yield f"event: state_update\ndata: {json.dumps(state)}\n\n"
                else:
                    logger.info("Update is wrong type")
                    break

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
