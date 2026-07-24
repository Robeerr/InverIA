"""
auth.py — JWT authentication for InverIA
Single-user: credentials stored in environment variables.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET", "inveria-dev-secret-change-in-prod-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

APP_USERNAME = os.environ.get("APP_USERNAME", "rober")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "inveria2024")  # fallback solo en dev

_DEFAULT_SECRET = "inveria-dev-secret-change-in-prod-please"

# GUARDARRAIL DE PRODUCCIÓN: un JWT_SECRET por defecto es FORJABLE (cualquiera firma sus
# propios tokens y anula toda la auth). En Render (que fija RENDER=true) nos negamos a
# arrancar sin secreto propio. En local se permite el default para desarrollar.
if os.environ.get("RENDER") and SECRET_KEY == _DEFAULT_SECRET:
    raise RuntimeError(
        "SEGURIDAD: falta la variable de entorno JWT_SECRET en produccion. Sin ella, los "
        "tokens de sesion son forjables y la autenticacion no protege nada. Define JWT_SECRET "
        "en Render con un valor aleatorio largo y vuelve a desplegar."
    )
# Aviso (no bloqueante) si en produccion se usa la contrasena por defecto sin hash.
if os.environ.get("RENDER") and not os.environ.get("APP_PASSWORD_HASH") and APP_PASSWORD == "inveria2024":
    import logging
    logging.getLogger("auth").warning(
        "SEGURIDAD: usando la contrasena por defecto. Define APP_PASSWORD_HASH (o APP_PASSWORD) en Render."
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _bcrypt_trunc(password: str) -> bytes:
    """bcrypt solo usa los primeros 72 bytes; las versiones nuevas lanzan error
    en vez de truncar. Truncamos nosotros para aceptar frases largas sin romper."""
    return password.encode("utf-8")[:72]


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_bcrypt_trunc(plain), hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(_bcrypt_trunc(password))


def authenticate_user(username: str, password: str) -> bool:
    if username.lower() != APP_USERNAME.lower():
        return False
    stored = os.environ.get("APP_PASSWORD_HASH")
    if stored:
        return verify_password(password, stored)
    # Fallback: compare plain (only for dev, set APP_PASSWORD_HASH in prod)
    return password == APP_PASSWORD


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency — returns username or raises 401."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Inicia sesión para continuar.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise ValueError("no sub")
        return username
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada o inválida. Vuelve a iniciar sesión.",
            headers={"WWW-Authenticate": "Bearer"},
        )
