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
    try:
        # Get request body
        body = await request.json()

        # Get headers
        headers = dict(request.headers)

        # Extract model name for logging
        model = proxy_service.extract_model_name(body)

        # Forward request to Anthropic
        status_code, response_headers, response_body = await proxy_service.forward_anthropic_request(
            endpoint="/v1/messages",
            method="POST",
            headers=headers,
            body=body
        )

        # If successful, record statistics
        if status_code == 200:
            # Extract token usage
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

        # Return Anthropic's response
        # Properly serialize response body to JSON if it's a dict
        if isinstance(response_body, str):
            content = response_body
        else:
            content = json.dumps(response_body)

        return Response(
            content=content,
            status_code=status_code,
            media_type="application/json",
            headers={k: v for k, v in response_headers.items() if k.lower() not in ['content-encoding', 'transfer-encoding']}
        )

    except Exception as e:
        # Log error and return 500
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
        except:
            pass  # Don't fail if we can't record the error

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Proxy error: {str(e)}"
        )
