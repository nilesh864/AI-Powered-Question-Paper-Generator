from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60
PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _bcrypt_password(password: str) -> str:
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return PASSWORD_CONTEXT.hash(_bcrypt_password(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_CONTEXT.verify(_bcrypt_password(password), password_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str) -> str:
    if role not in {"Teacher", "Admin"}:
        raise ValueError("Role must be Teacher or Admin.")
    expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    return jwt.encode({"sub": subject, "role": role, "exp": expires}, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, str] | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        role = payload.get("role")
        if not isinstance(subject, str) or role not in {"Teacher", "Admin"}:
            return None
        return {"sub": subject, "role": role}
    except JWTError:
        return None