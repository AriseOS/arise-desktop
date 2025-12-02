"""
Authentication API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database.connection import get_db_session
from ..services.user_service import get_user_service
from ..services.auth_service import get_auth_service
from .schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    UserInfoResponse,
    ErrorResponse,
)


router = APIRouter()
user_service = get_user_service()
auth_service = get_auth_service()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        409: {"model": ErrorResponse, "description": "User already exists"},
    }
)
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db_session)
):
    """Register a new user

    Creates a new user account with:
    - Unique username and email
    - Hashed password
    - Encrypted API key
    - Trial period (30 days, 100 workflow executions)

    Returns:
        RegisterResponse with user info and API key (only shown once)

    Raises:
        HTTPException 409: If username or email already exists
        HTTPException 400: If validation fails
    """
    try:
        # Create user
        user = user_service.create_user(
            db=db,
            username=request.username,
            email=request.email,
            password=request.password,
        )

        # Get API key (stored in plaintext)
        api_key = user.api_key

        # Return user info with API key
        return RegisterResponse(
            success=True,
            user=user.to_dict(include_api_key=False),
            api_key=api_key,
            message="User registered successfully. Please save your API key."
        )

    except IntegrityError as e:
        db.rollback()
        # Check which constraint was violated
        error_msg = str(e.orig).lower()
        if 'username' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists"
            )
        elif 'email' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User registration failed"
            )


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    }
)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db_session)
):
    """User login

    Authenticate user with username/email and password.

    Returns:
        LoginResponse with JWT token, user info, and masked API key

    Raises:
        HTTPException 401: If authentication fails
    """
    # Authenticate user
    user = user_service.authenticate_user(
        db=db,
        username=request.username,
        password=request.password
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password"
        )

    # Create JWT token
    token = auth_service.create_access_token(
        user_id=str(user.user_id),
        username=user.username,
        is_admin=user.is_admin
    )

    # Get masked API key
    plaintext_api_key = user_service.get_plaintext_api_key(user)

    return LoginResponse(
        success=True,
        token=token,
        user=user.to_dict(include_api_key=False),
        api_key=plaintext_api_key  # Will be masked in to_dict
    )


@router.get(
    "/me",
    response_model=UserInfoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    }
)
async def get_current_user(
    authorization: str = Depends(lambda: None),  # TODO: Implement proper auth dependency
    db: Session = Depends(get_db_session)
):
    """Get current user information

    Requires JWT token in Authorization header: Bearer <token>

    Returns:
        UserInfoResponse with current user information

    Raises:
        HTTPException 401: If token is invalid or expired
    """
    # TODO: Implement JWT token extraction and validation
    # For now, this is a placeholder
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )
