from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.security import decode_access_token


def rate_limit_key(request: Request) -> str:
    """Key by the authenticated user's identity so limits track per-user usage,
    falling back to client IP for unauthenticated requests."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        subject = decode_access_token(auth_header[7:])
        if subject:
            return f"user:{subject}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many analyze requests. Please wait a minute and try again."},
    )
