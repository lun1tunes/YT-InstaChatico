from contextlib import asynccontextmanager
import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import uvicorn
from starlette.responses import Response

from api_v1 import router as router_v1
from api_v1.docs.views import create_docs_router
from api_v1.comments.views import JsonApiError, json_api_error_handler, validation_error_handler
from core.config import settings
from core.logging_config import configure_logging, trace_id_ctx
import uuid
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


class LoggingCORSMiddleware(CORSMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        method = request.method
        response: Response = await super().dispatch(request, call_next)

        if origin:
            allowed_origin = response.headers.get("access-control-allow-origin")
            if allowed_origin:
                logger.debug(
                    "CORS request allowed | origin=%s | method=%s | allow_credentials=%s",
                    origin,
                    method,
                    settings.cors_allow_credentials,
                )
            else:
                logger.warning(
                    "CORS request denied or not matched | origin=%s | method=%s",
                    origin,
                    method,
                )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Application starting up...")
    logger.info(
        "CORS configuration | origins=%s | allow_credentials=%s",
        settings.cors_allowed_origins,
        settings.cors_allow_credentials,
    )

    from core.container import get_container
    container = get_container()
    instagram_service = container.instagram_service()
    logger.info("Instagram service initialized")

    yield

    logger.info("Application shutting down...")
    await instagram_service.close()
    logger.info("Instagram service session closed")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    LoggingCORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router=router_v1, prefix=settings.api_v1_prefix)
docs_router = create_docs_router(app)
app.include_router(router=docs_router)
app.add_exception_handler(JsonApiError, json_api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


# Middleware для проверки X-Hub подписи
@app.middleware("http")
async def verify_webhook_signature(request: Request, call_next):
    # Assign/propagate a trace id for each request
    incoming_trace = request.headers.get("X-Trace-Id")
    trace_id = incoming_trace or str(uuid.uuid4())
    token = trace_id_ctx.set(trace_id)
    # Check if this is a POST request to the webhook endpoint (with or without trailing slash)
    webhook_path = "/api/v1/webhook"
    if request.method == "POST" and request.url.path.rstrip("/") == webhook_path:
        # Instagram uses X-Hub-Signature-256 (SHA256) instead of X-Hub-Signature (SHA1)
        signature_256 = request.headers.get("X-Hub-Signature-256")
        signature_1 = request.headers.get("X-Hub-Signature")
        body = await request.body()

        # Try SHA256 first (Instagram's preferred method), then fallback to SHA1
        signature = signature_256 or signature_1

        if signature:
            # Determine which algorithm to use based on the header
            if signature_256:
                # Instagram uses SHA256
                expected_signature = (
                    "sha256=" + hmac.new(settings.app_secret.encode(), body, hashlib.sha256).hexdigest()
                )
            else:
                # Fallback to SHA1 for compatibility
                expected_signature = "sha1=" + hmac.new(settings.app_secret.encode(), body, hashlib.sha1).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logging.error("Signature verification failed!")
                logging.error(f"Body length: {len(body)}")
                logging.error(f"Signature header used: {'X-Hub-Signature-256' if signature_256 else 'X-Hub-Signature'}")
                logging.error(
                    f"Signature prefix: {signature[:10]}..." if len(signature) > 10 else "Signature: [REDACTED]"
                )
                return JSONResponse(status_code=401, content={"detail": "Invalid signature"})
            else:
                logging.info("Signature verification successful")
        else:
            # Check if we're in development mode (allow requests without signature for testing)
            development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"

            if development_mode:
                logging.warning("DEVELOPMENT MODE: Allowing webhook request without signature header")
            else:
                # Block requests without signature headers in production
                logging.error(
                    "Webhook request received without X-Hub-Signature or X-Hub-Signature-256 header - blocking request"
                )
                return JSONResponse(status_code=401, content={"detail": "Missing signature header"})

        # Сохраняем тело запроса для дальнейшей обработки
        request.state.body = body
        return await call_next(request)
    try:
        response = await call_next(request)
    finally:
        trace_id_ctx.reset(token)
    # Include trace id in response for clients to propagate
    response.headers["X-Trace-Id"] = trace_id
    return response


if __name__ == "__main__":

    port = int(os.getenv("PORT"))
    host = os.getenv("HOST", "0.0.0.0")  # Allow external connections
    uvicorn.run("main:app", host=host, port=port, reload=True)
