import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt

from src.auth.models import TokenData
from src.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    JWT_SECRET_FILE_PATH,
)
from src.core.logger import get_logger

logger = get_logger("Auth.JWT")


def get_jwt_secret() -> str:
    """
    Retrieve JWT secret key from environment or persisted file.
    Generates a secure random 256-bit secret if not present.
    """
    if JWT_SECRET_KEY and JWT_SECRET_KEY.strip():
        return JWT_SECRET_KEY.strip()

    # Try reading from secret file
    if os.path.exists(JWT_SECRET_FILE_PATH):
        try:
            with open(JWT_SECRET_FILE_PATH, "r", encoding="utf-8") as f:
                stored_secret = f.read().strip()
                if stored_secret:
                    return stored_secret
        except (IOError, PermissionError) as e:
            logger.warning(f"Could not read JWT secret file: {e}")

    # Generate and persist new secret
    new_secret = secrets.token_urlsafe(32)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(JWT_SECRET_FILE_PATH)), exist_ok=True)
        with open(JWT_SECRET_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_secret)
        logger.info(f"Generated new persistent JWT secret at {JWT_SECRET_FILE_PATH}")
    except (IOError, PermissionError, OSError) as e:
        logger.warning(f"Failed to persist JWT secret to file: {e}")

    return new_secret


_SECRET = get_jwt_secret()


def create_access_token(username: str, role: str, expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """
    Generate signed JWT access token.
    Returns (token_str, expires_in_seconds).
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
        expires_in = int(expires_delta.total_seconds())
    else:
        expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": username,
        "role": role,
        "type": "access",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, _SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt, expires_in


def create_refresh_token(username: str, role: str) -> tuple[str, int]:
    """
    Generate signed JWT refresh token with longer expiry.
    Returns (token_str, expires_in_seconds).
    """
    expires_in = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": username,
        "role": role,
        "type": "refresh",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, _SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt, expires_in


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode JWT token. Returns TokenData or None if invalid/expired.
    """
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        exp: int = payload.get("exp")
        token_type: str = payload.get("type", "access")
        if not username or not role:
            return None
        return TokenData(username=username, role=role, exp=exp, token_type=token_type)
    except jwt.ExpiredSignatureError:
        logger.debug("Token has expired")
        return None
    except jwt.PyJWTError as e:
        logger.debug(f"Invalid JWT token: {e}")
        return None


def decode_refresh_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode JWT refresh token. Returns TokenData or None if invalid/expired.
    Only accepts tokens with type='refresh'.
    """
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        token_type: str = payload.get("type")
        if not username or not role or token_type != "refresh":
            return None
        return TokenData(username=username, role=role, exp=payload.get("exp"), token_type="refresh")
    except jwt.ExpiredSignatureError:
        logger.debug("Refresh token has expired")
        return None
    except jwt.PyJWTError as e:
        logger.debug(f"Invalid refresh token: {e}")
        return None
