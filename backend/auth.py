"""
auth.py — JWT authentication for InverIA
Single-user: credentials stored in environment variables.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
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
# ── Guardarraíl de la contraseña en producción ────────────────────────────────
# Mientras esto sea False, la falta de APP_PASSWORD_HASH solo AVISA: es el
# comportamiento de hoy y no puede romper un despliegue en marcha. Se pone a True
# cuando la variable esté configurada en Render, y entonces arrancar sin ella pasa a
# ser imposible — igual que ya ocurre con JWT_SECRET.
#
# La comprobación vive en una función aparte para poder probarla en los dos estados
# sin depender de reimportar el módulo con el entorno trucado.
EXIGIR_HASH_EN_PRODUCCION = False


def motivo_para_no_arrancar(en_produccion: bool, hash_configurado: bool,
                            password_por_defecto: bool, exigir: bool) -> Optional[str]:
    """El motivo por el que NO se debe arrancar, o None si se puede.

    Solo bloquea en producción: en local la contraseña por defecto es una comodidad
    y no un riesgo, porque no hay nada expuesto que proteger.
    """
    if not en_produccion:
        return None
    if hash_configurado:
        return None
    if exigir:
        return ("SEGURIDAD: falta la variable de entorno APP_PASSWORD_HASH en produccion. "
                "Genera el hash con `python scripts/generar_hash.py` y defínela en Render.")
    if password_por_defecto:
        return ("SEGURIDAD: usando la contrasena por defecto, que es publica y esta en el "
                "repositorio. Define APP_PASSWORD_HASH en Render.")
    return None


_motivo = motivo_para_no_arrancar(
    en_produccion=bool(os.environ.get("RENDER")),
    hash_configurado=bool(os.environ.get("APP_PASSWORD_HASH")),
    password_por_defecto=(APP_PASSWORD == "inveria2024"),
    exigir=EXIGIR_HASH_EN_PRODUCCION,
)
if _motivo:
    if EXIGIR_HASH_EN_PRODUCCION:
        raise RuntimeError(_motivo)
    import logging
    logging.getLogger("auth").warning(_motivo)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# bcrypt solo usa los primeros 72 bytes de la contraseña; el resto lo ignora. Desde
# la versión 4.1 la librería, en vez de truncar en silencio, LANZA — que es la
# decisión correcta, porque truncar callando hace creer que una frase larguísima
# aporta seguridad que no aporta. Truncamos nosotros, en un solo sitio y de forma
# explícita, y avisamos donde toca.
BCRYPT_MAX_BYTES = 72


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str


# ── Contraseñas ───────────────────────────────────────────────────────────────
# Se usa `bcrypt` DIRECTAMENTE, sin passlib. Passlib se quitó porque estaba roto de
# dos formas independientes, no por preferencia:
#
#   1. Lee `bcrypt.__about__.__version__` para detectar la versión del backend, y
#      bcrypt eliminó ese atributo en la 4.1. Al fallar la detección, passlib hace
#      una autocomprobación del backend hasheando una cadena larga de prueba, que
#      bcrypt ≥4.1 rechaza. Resultado: "password cannot be longer than 72 bytes"
#      con CUALQUIER contraseña, incluso de cuatro letras. El mensaje señala a la
#      contraseña, que es justo donde no está el problema.
#   2. Importa el módulo `crypt`, retirado de la biblioteca estándar en Python 3.13.
#
# La última versión de passlib es de 2020. No es una dependencia que vaya a
# arreglarse, y aquí solo aportaba cuatro líneas de envoltorio.
#
# Los hashes NO cambian de formato: passlib generaba `$2b$12$…` con la librería
# bcrypt por debajo, exactamente lo mismo que se genera ahora. Los que ya existan
# siguen validando.


def _bcrypt_trunc(password: str) -> bytes:
    """Los bytes con los que se hashea de verdad: UTF-8 recortado a 72.

    Se recorta en BYTES y no en caracteres porque ese es el límite real de bcrypt.
    Un corte puede partir un carácter multibyte por la mitad y dejar bytes que no
    son UTF-8 válido; da igual, porque bcrypt trabaja con bytes y aquí se aplica la
    MISMA función al generar y al verificar. Lo que no puede pasar es que una parte
    trunque y la otra no: ahí es donde nace un hash que nunca valida.
    """
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def excede_limite_bcrypt(password: str) -> bool:
    """¿Sobran bytes que bcrypt va a ignorar? Para poder avisar al generar el hash."""
    return len(password.encode("utf-8")) > BCRYPT_MAX_BYTES


def verify_password(plain: str, hashed: str) -> bool:
    """¿Coincide la contraseña con el hash? Nunca lanza: un hash corrupto es un 'no'.

    Devolver False en vez de propagar es lo correcto aquí: si la variable de entorno
    trae un hash mal pegado —recortado, con comillas, con un salto de línea—, lo que
    debe pasar es que no se pueda entrar, no que el endpoint de login devuelva un 500
    que además delata que el hash está mal formado.
    """
    if not hashed or not isinstance(hashed, str):
        return False
    try:
        return bcrypt.checkpw(_bcrypt_trunc(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """Hash bcrypt listo para pegar en APP_PASSWORD_HASH.

    `gensalt()` usa 12 rondas por defecto, las mismas que usaba passlib, así que el
    coste de verificación no cambia.
    """
    return bcrypt.hashpw(_bcrypt_trunc(password), bcrypt.gensalt()).decode("ascii")


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
