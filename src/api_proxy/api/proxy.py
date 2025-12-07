"""
LLM proxy API endpoints (Anthropic-compatible)
"""
import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..database.connection import get_db_session
from ..services.user_service import get_user_service
from ..services.proxy_service import get_proxy_service
from ..services.stats_service import get_stats_service
from .schemas import ErrorResponse


router = APIRouter()
user_service = get_user_service()
proxy_service = get_proxy_service()
stats_service = get_stats_service()


async def validate_api_key(
    x_api_key: str = Header(..., alias="x-api-key"),
    db: Session = Depends(get_db_session)
):
    """Dependency to validate API key

    Extracts API key from x-api-key header and validates it.

    Returns:
        User object if valid

    Raises:
        HTTPException 401: If API key is invalid or missing
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Provide it in x-api-key header."
        )

    # Validate API key
    user = user_service.validate_api_key(db, x_api_key)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return user


@router.post(
    "/v1/messages",
    responses={
        200: {"description": "Successful response (Anthropic-compatible)"},
        401: {"model": ErrorResponse, "description": "Invalid API key"},
        500: {"model": ErrorResponse, "description": "Proxy error"},
    }
)
async def proxy_messages(
    request: Request,
    user = Depends(validate_api_key),
    db: Session = Depends(get_db_session)
):
    """Proxy Anthropic Messages API

    This endpoint is 100% compatible with Anthropic's /v1/messages API.
    It forwards requests to Anthropic and tracks token usage.

    Request format: https://docs.anthropic.com/claude/reference/messages_post

    Flow:
    1. Validate user's API key
    2. Forward request to Anthropic with system key
    3. Extract token usage from response
    4. Record statistics in database
    5. Return response to caller

    Headers:
        x-api-key: User's Ami API key (ami_xxx)

    Body:
        Same as Anthropic Messages API

    Returns:
        Same as Anthropic Messages API (with usage info)
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Log incoming request
        logger.info(f"[PROXY] Incoming request URL: {request.url}")
        logger.info(f"[PROXY] Query string: {request.url.query}")

        # Get request body
        body = await request.json()
        logger.info(f"[PROXY] Request body keys: {list(body.keys())}")

        # Get headers
        headers = dict(request.headers)

        # Extract model name for logging
        model = proxy_service.extract_model_name(body)

        # Build endpoint with query parameters
        endpoint = "/v1/messages"
        if request.url.query:
            endpoint = f"{endpoint}?{request.url.query}"

        logger.info(f"[PROXY] Forwarding to endpoint: {endpoint}")

        # Forward request to Anthropic
        status_code, response_headers, response_body = await proxy_service.forward_anthropic_request(
            endpoint=endpoint,
            method="POST",
            headers=headers,
            body=body
        )

        logger.info(f"[PROXY] Response status: {status_code}")

        # If successful, record statistics
        if status_code == 200:
            # Extract token usage from parsed response
            input_tokens, output_tokens = proxy_service.extract_token_usage(response_body)

            # Record API call
            stats_service.record_api_call(
                db=db,
                user_id=user.user_id,
                provider="anthropic",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_type=None,  # Can be set by caller via custom header
                success=True,
            )

        # Return response (proxy_service already decompressed and parsed)
        # Serialize back to JSON for client
        if isinstance(response_body, str):
            content = response_body
        else:
            content = json.dumps(response_body)

        return Response(
            content=content,
            status_code=status_code,
            media_type="application/json",
            # Remove compression headers since we're returning decompressed JSON
            headers={k: v for k, v in response_headers.items() if k.lower() not in ['content-encoding', 'transfer-encoding']}
        )

    except Exception as e:
        # Log error and return 500
        logger.error(f"[PROXY] Error occurred: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"[PROXY] Traceback:\n{traceback.format_exc()}")

        # Record failed API call
        try:
            stats_service.record_api_call(
                db=db,
                user_id=user.user_id,
                provider="anthropic",
                model=body.get('model', 'unknown') if 'body' in locals() else 'unknown',
                input_tokens=0,
                output_tokens=0,
                success=False,
                error_message=str(e),
            )
        except Exception as stats_error:
            logger.error(f"[PROXY] Failed to record stats: {stats_error}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Proxy error: {str(e)}"
        )
