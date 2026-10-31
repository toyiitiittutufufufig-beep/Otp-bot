"""
╔══════════════════════════════════════════════════════════════╗
║  Configuration Loader - يقرأ كل الإعدادات من .env بأمان     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# تحميل .env من نفس مجلد المشروع
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get(key: str, default=None, required: bool = False):
    """قراءة متغير مع فحص"""
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise ValueError(f"❌ المتغير {key} مطلوب في ملف .env")
    return value


def _get_list(key: str, cast=str) -> list:
    """قراءة قائمة مفصولة بفواصل"""
    raw = os.getenv(key, "")
    if not raw:
        return []
    return [cast(x.strip()) for x in raw.split(",") if x.strip()]


class Config:
    """كل إعدادات التطبيق في مكان واحد"""

    # ─── Telegram ────────────────────────────────────────────
    BOT_TOKEN: str = _get("BOT_TOKEN", "")
    ADMIN_IDS: list = _get_list("ADMIN_IDS", int)
    CHAT_IDS: list = _get_list("CHAT_IDS", str)

    # ─── IVASMS ──────────────────────────────────────────────
    IVASMS_EMAIL: str = _get("IVASMS_EMAIL", "")
    IVASMS_PASSWORD: str = _get("IVASMS_PASSWORD", "")
    IVASMS_BASE_URL: str = "https://ivas.tempnum.qzz.io"
    IVASMS_LOGIN_URL: str = f"{IVASMS_BASE_URL}/login"
    IVASMS_SMS_API: str = f"{IVASMS_BASE_URL}/portal/sms/received/getsms"

    # ─── Security ────────────────────────────────────────────
    SESSION_SECRET: str = _get("SESSION_SECRET", secrets.token_hex(32))

    # ─── Database ────────────────────────────────────────────
    DATABASE_URL: str = _get("DATABASE_URL", "sqlite:///bot.db")

    # ─── Bot Behavior ────────────────────────────────────────
    REFRESH_INTERVAL: int = int(_get("REFRESH_INTERVAL", "3"))
    CACHE_EXPIRE_MINUTES: int = int(_get("CACHE_EXPIRE_MINUTES", "30"))
    DEBUG: bool = _get("DEBUG", "0") == "1"

    # ─── Validation ──────────────────────────────────────────
    @classmethod
    def validate(cls) -> list:
        """ترجع قائمة بالمشاكل لو فيه"""
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN غير موجود")
        if not cls.ADMIN_IDS:
            errors.append("ADMIN_IDS غير موجود")
        if not cls.CHAT_IDS:
            errors.append("CHAT_IDS غير موجود")
        if not cls.IVASMS_EMAIL:
            errors.append("IVASMS_EMAIL غير موجود")
        if not cls.IVASMS_PASSWORD:
            errors.append("IVASMS_PASSWORD غير موجود")
        return errors

    @classmethod
    def is_ready(cls) -> bool:
        return len(cls.validate()) == 0


# نسخة جاهزة للاستخدام
config = Config()