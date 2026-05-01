from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from app.core.config import settings

bearer_scheme = HTTPBearer()


class CurrentUser(BaseModel):
    user_id: UUID
    email: str
    role: str
    employee_id: Optional[UUID] = None  # ← добавляем


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_iss": False}
        )
        user_id: str = payload.get("sub")
        email: str = payload.get("email", "")
        role: str = (payload.get("role") or "EMPLOYEE").upper()
        # ← берём employeeId прямо из токена ядра
        employee_id_str: str = payload.get("employeeId")

        if not user_id:
            raise credentials_exception

        return CurrentUser(
            user_id=UUID(user_id),
            email=email,
            role=role,
            employee_id=UUID(employee_id_str) if employee_id_str else None,
        )

    except JWTError:
        raise credentials_exception


def require_roles(*roles: str):
    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_role_upper = user.role.upper()
        allowed_upper = [r.upper() for r in roles]
        if user_role_upper not in allowed_upper:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {list(roles)}, your role: {user.role}"
            )
        return user
    return Depends(checker)


AnyEmployee    = Depends(get_current_user)
ManagerOnly    = require_roles("MANAGER", "ADMIN")
AdminOnly      = require_roles("ADMIN")
ShiftManagerPlus = require_roles("SHIFT_MANAGER", "MANAGER", "ADMIN")