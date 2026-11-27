import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return parsed


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in .env")

try:
    ADMIN_ID = int(os.environ["ADMIN_ID"])
except (KeyError, ValueError) as exc:
    raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID") from exc

EXPECTED_BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@").lower()
SUPPORT_HANDLE = os.getenv("SUPPORT_HANDLE", "guybit5")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PRICE_STARS = env_int("PRICE_STARS", 50, 1, 25_000)
PREVIEW_SECONDS = env_int("PREVIEW_SECONDS", 30, 1, 600)
MAX_UPLOAD_BYTES = env_int("MAX_UPLOAD_MIB", 19, 1, 50) * 1024 * 1024
