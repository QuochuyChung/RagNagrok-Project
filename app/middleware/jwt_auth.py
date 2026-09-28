from typing import Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Match

from app.core.security import (
    decode_access_token,
    get_required_roles,
    is_public_path,
    is_public_endpoint
)


def _find_matched_route(routes, scope):
    """
        Nhận vào danh sách toàn bộ route có trong app và tìm ra các route khớp
        + Phải đổi bởi vì cái routes tự khai báo được bọc trong 1 object _IncludeRoute nên phải'
        tìm bên trong object đó
        => Trả ra route được tìm thấy
    """
    for route in routes:
        # trả ra 1 Match.FULL, với 1 child
        match, _ = route.matches(scope)
        if match != Match.FULL:
            continue

        # Nếu đây là các route thuần của thư viện mà không thông qua khai báo như /docs
        # -> Thì không có được bọc 1 object IncludeRoutes, nên tìm thẳng trên endpoint luôn
        if getattr(route, "endpoint", None) is not None:
            return route # trả ra route luôn

        # Lấy ra cái route thông qua object "original_route" bên trong IncludeRoute
        nested_route = getattr(route, "original_router", None)
        # đã lấy ra được chính xác cái route
        if nested_route is not None:
            route_found_in_include = _find_matched_route(nested_route.routes, scope)

            if route_found_in_include is not None:
                return route_found_in_include

    return None






class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Pass CORS OPTIONS preflight requests through to CORSMiddleware
        if request.method == "OPTIONS":
            return await call_next(request)

        if is_public_path(request.url.path):
            return await call_next(request)

        # Tìm route nào sẽ xử lí request
        matched_route = _find_matched_route(request.app.routes, request.scope)

        if matched_route is None:
            return await call_next(request)  # để route trả 404

        endpoint = getattr(matched_route, 'endpoint', None)

        # bắt route public
        if is_public_endpoint(endpoint):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error_code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header."},
            )

        try:
            payload = decode_access_token(auth_header.removeprefix("Bearer ").strip())
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"error_code": "TOKEN_EXPIRED", "message": "Token has expired."},
            )
        except jwt.PyJWTError:
            return JSONResponse(
                status_code=401,
                content={"error_code": "INVALID_TOKEN", "message": "Invalid authentication token."},
            )

        required = get_required_roles(endpoint)
        # Nếu Role trong payload không có trong list required
        if required and payload.get("role") not in required:
            return JSONResponse(
                status_code=403,
                content={"error_code": "FORBIDDEN", "message": "Access forbidden for this role."},
            )

        raw_tenant_id = payload.get("tenant_id")
        request.state.tenant_id = str(raw_tenant_id) if raw_tenant_id else None
        request.state.user_id = payload.get("sub")
        request.state.role = payload.get("role")

        return await call_next(request)






