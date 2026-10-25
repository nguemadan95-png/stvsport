import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from jose import jwt, JWTError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # le .env est lu AVANT de calculer la clé secrète

ALGORITHM = "HS256"
TOKEN_MINUTES = 60 * 24 * 7
_PLACEHOLDERS = {"", "CHANGE-ME-WITH-A-LONG-RANDOM-SECRET", "CHANGE-ME-STV-SPORT-LOCAL-SECRET-2026"}


def _load_secret() -> str:
    value = os.getenv("STV_SECRET_KEY", "").strip()
    if value not in _PLACEHOLDERS:
        return value
    # Aucune clé valide dans .env : on en génère une et on la conserve localement.
    key_file = ROOT / "secret.key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(48)
    key_file.write_text(key)
    return key


SECRET_KEY = _load_secret()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 240000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def create_token(user_id: int, is_admin: bool):
    exp = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": str(user_id), "admin": is_admin, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
