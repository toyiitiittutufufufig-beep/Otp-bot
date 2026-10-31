#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Run - نقطة التشغيل الرئيسية                                ║
║  بيشغل: Flask + Telegram Bot + OTP Monitor                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import logging

from config import config
from app import create_app

# ══════════════════════════════════════════════════════════════
#  Logging
# ══════════════════════════════════════════════════════════════
log_level = logging.DEBUG if config.DEBUG else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run")


# ══════════════════════════════════════════════════════════════
#  التحقق من الإعدادات
# ══════════════════════════════════════════════════════════════
def validate_config() -> bool:
    errors = config.validate()
    if errors:
        logger.error("=" * 60)
        logger.error("❌ إعدادات ناقصة في .env:")
        for err in errors:
            logger.error(f"   - {err}")
        logger.error("=" * 60)
        return False
    return True


# ══════════════════════════════════════════════════════════════
#  تشغيل كل المكونات
# ══════════════════════════════════════════════════════════════
def main():
    logger.info("=" * 60)
    logger.info("🚀 24XRAVEN SMS BOT - Starting...")
    logger.info("=" * 60)

    if not validate_config():
        logger.error("⛔ التوقف بسبب إعدادات ناقصة")
        sys.exit(1)

    logger.info("✅ Config loaded")
    logger.info(f"   - Admins: {len(config.ADMIN_IDS)}")
    logger.info(f"   - Groups: {len(config.CHAT_IDS)}")
    logger.info(f"   - Refresh: {config.REFRESH_INTERVAL}s")
    db_type = "PostgreSQL" if "postgres" in config.DATABASE_URL else "SQLite"
    logger.info(f"   - Database: {db_type}")

    # 1. إنشاء Flask app
    logger.info("📦 Creating Flask app...")
    app = create_app()
    logger.info("✅ Flask app ready")

    # 2. تسجيل app context في OTP Monitor (مهم!)
    try:
        from otp_monitor import set_app
        set_app(app)
        logger.info("✅ OTP Monitor app context registered")
    except Exception as e:
        logger.error(f"❌ فشل تسجيل app context: {e}")

    # 3. تسجيل admin handlers + بدء البوت
    logger.info("🤖 Initializing Telegram bot...")
    try:
        from telegram_bot import init_bot, start_bot_thread
        init_bot()
        start_bot_thread()
        logger.info("✅ Telegram bot running")
    except Exception as e:
        logger.error(f"❌ فشل بدء Telegram bot: {e}")
        logger.exception(e)
        sys.exit(1)

    # 4. بدء OTP Monitor
    logger.info("👁️ Starting OTP monitor...")
    try:
        from otp_monitor import start_monitor
        result = start_monitor()
        logger.info(f"   {result}")
    except Exception as e:
        logger.error(f"❌ فشل بدء OTP Monitor: {e}")
        logger.exception(e)

    # 5. تشغيل Flask
    port = int(os.environ.get("PORT", "5000"))
    logger.info("=" * 60)
    logger.info(f"🌐 Flask listening on 0.0.0.0:{port}")
    logger.info("=" * 60)

    try:
        app.run(
            host="0.0.0.0",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("⏹️ Keyboard interrupt - shutting down...")
        shutdown()
    except Exception as e:
        logger.error(f"❌ Flask crashed: {e}")
        logger.exception(e)
        shutdown()
        sys.exit(1)


def shutdown():
    """إيقاف نظيف"""
    logger.info("🛑 Shutting down...")
    try:
        from otp_monitor import stop_monitor
        stop_monitor()
        logger.info("   ✅ OTP Monitor stopped")
    except Exception as e:
        logger.warning(f"   ⚠️ خطأ في إيقاف المراقبة: {e}")


# ══════════════════════════════════════════════════════════════
#  نقطة الدخول
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        logger.exception(e)
        sys.exit(1)