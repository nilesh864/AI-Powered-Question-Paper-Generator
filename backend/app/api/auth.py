from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.mongodb import collection
from app.models.user import UserCreate, UserLogin

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def public_user(user: dict) -> dict:
    return {"id": user["_id"], "name": user["name"], "email": user["email"], "role": user.get("role", "Teacher"), "department": user.get("department", ""), "is_active": user.get("is_active", True), "created_at": user["created_at"]}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate):
    users = collection("users")
    if await users.find_one({"email": payload.email.lower()}):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = {"_id": str(uuid4()), "name": payload.name.strip(), "email": payload.email.lower(), "password_hash": hash_password(payload.password), "role": "Teacher", "department": payload.department.strip(), "is_active": True, "created_at": datetime.now(timezone.utc)}
    await users.insert_one(user)
    return {"access_token": create_access_token(user["_id"], user["role"]), "token_type": "bearer", "user": public_user(user)}


@router.post("/login")
async def login(payload: UserLogin):
    user = await collection("users").find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user.get("password_hash", "")) or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    role = user.get("role", "Teacher")
    if role not in {"Teacher", "Admin"}:
        raise HTTPException(status_code=401, detail="Account role is invalid.")
    return {"access_token": create_access_token(user["_id"], role), "token_type": "bearer", "user": public_user(user)}


async def current_user(token: str = Depends(oauth2_scheme)) -> dict:
    claims = decode_access_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired access token.", headers={"WWW-Authenticate": "Bearer"})
    user = await collection("users").find_one({"_id": claims["sub"]})
    if not user or not user.get("is_active", True) or user.get("role", "Teacher") != claims["role"]:
        raise HTTPException(status_code=401, detail="Account is unavailable or token permissions have changed.", headers={"WWW-Authenticate": "Bearer"})
    user.setdefault("role", "Teacher")
    user.setdefault("department", "")
    user.setdefault("is_active", True)
    return user


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)