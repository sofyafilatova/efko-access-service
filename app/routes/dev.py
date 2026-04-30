from fastapi import APIRouter
from jose import jwt
from datetime import datetime, timedelta
from app.core.config import settings

router = APIRouter(prefix="/dev", tags=["Dev only"])


@router.post("/token")
def generate_test_token(
    user_id: str = "00000000-0000-0000-0000-000000000001",
    email: str = "test@efko.ru",
    role: str = "ADMIN"
):
    """Только для разработки. Удалить перед продом."""
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {"access_token": token, "token_type": "bearer"}