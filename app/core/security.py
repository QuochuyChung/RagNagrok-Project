from collections.abc import Callable
from datetime import datetime, timezone, timedelta

from fastapi.security import HTTPBearer

from app.core.config import get_settings
import jwt

from app.models import Users

bearer_scheme = HTTPBearer(auto_error=False)

# CÁC LIST GHI LẠI LÚC START APP
_PUBLIC_ENDPOINTS: set[Callable] = set() # những route không cần jwt
_PUBLIC_PATH: set[str] = {"/docs", "/redoc", "/openapi.json"} # route FastAPI tự sinh
_ROUTE_ROLES: dict[Callable, set[str]] = {}


"""
Những decorator mà app sẽ chạy lần đầu khi start dùng để add endpoint 
và các roles có thể làm được gì trong những endpoint đó
"""

# Decorator dùng để add các public endpoint/routes vào
def public(func: Callable) -> Callable:
    _PUBLIC_ENDPOINTS.add(func)
    return func


# Decorator dùng để add các roles vào
def requires_roles(*roles: str) -> Callable:
    if not roles:
        raise ValueError("requires_roles() need at least one role ")
    def decorator(func: Callable) -> Callable:
        _ROUTE_ROLES[func] = set(roles)

        return func

    return decorator


# Helper để middleware xài
def is_public_path(path: str) -> bool:
   return path in _PUBLIC_PATH


def is_public_endpoint(func: Callable | None) -> bool:
    return func in _PUBLIC_ENDPOINTS


def get_required_roles(func: Callable | None) -> set[str] | None:
    return _ROUTE_ROLES.get(func)


def create_access_token(user: Users) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user.user_id),
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "role": user.role.role_name,
        "username": user.user_name,
        "full_name": user.full_name,
        "exp": datetime.now(timezone.utc)+ timedelta(minutes=settings.jwt_expired_minutes),
    }

    token = jwt.encode(payload=payload, key=settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    return token

def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, key=settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])



