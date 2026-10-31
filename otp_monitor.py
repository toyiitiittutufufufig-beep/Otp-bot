"""
╔══════════════════════════════════════════════════════════════╗
║  OTP Monitor - بيربط scraper بـ telegram_bot                ║
║  - يجلب OTPs كل REFRESH_INTERVAL ثانية                     ║
║  - يمنع التكرار باستخدام message_hash (في الداتابيز)        ║
║  - يبعت للمستخدم صاحب الرقم + للجروبات                      ║
║  - يسجل في OTPLog                                          ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import logging
import threading
from datetime import datetime

from config import config
from models import db, User, OTPLog
from scraper import IVASMSScraper
from utils import now_str

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  Flask app context (بيتحدد من run.py)
# ══════════════════════════════════════════════════════════════
_app = None


def set_app(app):
    """يتنادى من run.py بعد create_app()"""
    global _app
    _app = app
    logger.info("✅ OTP Monitor: app context registered")


def _get_app():
    global _app
    if _app is None:
        # fallback: حاول تعمل app جديد
        try:
            from app import create_app
            _app = create_app()
            logger.warning("⚠️ OTP Monitor: created fallback app context")
        except Exception as e:
            logger.error(f"❌ فشل إنشاء app context: {e}")
    return _app


class OTPMonitor:
    """مراقب OTPs - بيشتغل في thread منفصل"""

    def __init__(self):
        self.scraper = IVASMSScraper()
        self.is_running = False
        self.thread = None
        self.stats = {
            "total_fetched": 0,
            "total_sent_user": 0,
            "total_sent_group": 0,
            "total_duplicates": 0,
            "total_errors": 0,
            "last_check": None,
            "started_at": None,
        }

    # ══════════════════════════════════════════════════════════
    #  بدء / إيقاف
    # ══════════════════════════════════════════════════════════
    def start(self) -> str:
        if self.is_running:
            return "⚠️ المراقبة شغالة بالفعل"
        self.is_running = True
        self.stats["started_at"] = datetime.utcnow()
        self.thread = threading.Thread(
            target=self._loop, daemon=True, name="otp-monitor"
        )
        self.thread.start()
        logger.info("✅ OTP Monitor started")
        return "✅ تم بدء المراقبة"

    def stop(self) -> str:
        if not self.is_running:
            return "⚠️ المراقبة متوقفة بالفعل"
        self.is_running = False
        logger.info("⏹️ OTP Monitor stopped")
        return "⏹️ تم إيقاف المراقبة"

    # ══════════════════════════════════════════════════════════
    #  الحلقة الرئيسية
    # ══════════════════════════════════════════════════════════
    def _loop(self):
        logger.info(f"🔄 بدء حلقة المراقبة كل {config.REFRESH_INTERVAL} ثانية")
        while self.is_running:
            try:
                self._check_once()
            except Exception as e:
                self.stats["total_errors"] += 1
                logger.error(f"خطأ في حلقة المراقبة: {e}")
                time.sleep(30)
                continue
            time.sleep(config.REFRESH_INTERVAL)
        logger.info("👋 حلقة المراقبة انتهت")

    # ══════════════════════════════════════════════════════════
    #  فحص واحد
    # ══════════════════════════════════════════════════════════
    def _check_once(self):
        """يجلب رسائل، يفلتر الجديد، يبعت"""
        from telegram_bot import send_otp_to_user, send_otp_to_groups

        self.stats["last_check"] = now_str()

        # 1. جلب الرسائل
        messages = self.scraper.fetch_messages()
        if not messages:
            return

        self.stats["total_fetched"] += len(messages)

        # 2. فلترة الجديد — جوه app_context
        new_messages = []
        app = _get_app()
        if app is None:
            logger.error("❌ app context غير متاح، لا يمكن الفلترة")
            return

        with app.app_context():
            for msg in messages:
                exists = db.session.query(OTPLog).filter_by(
                    message_hash=msg["hash"]
                ).first()
                if exists:
                    self.stats["total_duplicates"] += 1
                    continue
                new_messages.append(msg)

        if not new_messages:
            return

        logger.info(f"🆕 {len(new_messages)} رسالة جديدة")

        # 3. معالجة كل رسالة
        for msg in new_messages:
            try:
                self._process_message(msg, send_otp_to_user, send_otp_to_groups)
            except Exception as e:
                self.stats["total_errors"] += 1
                logger.error(f"خطأ في معالجة رسالة: {e}")

    # ══════════════════════════════════════════════════════════
    #  معالجة رسالة واحدة
    # ══════════════════════════════════════════════════════════
    def _process_message(self, msg, send_user_fn, send_group_fn):
        """يسجل + يبعت للمستخدم + يبعت للجروبات"""
        number = msg["number"]
        otp = msg["otp"]
        service = msg["service"]
        text = msg["text"]
        msg_hash = msg["hash"]

        app = _get_app()

        # 1. البحث عن المستخدم صاحب الرقم
        user_id = None
        if app:
            with app.app_context():
                user = db.session.query(User).filter_by(assigned_number=number).first()
                if user:
                    user_id = user.user_id

        # 2. إرسال للمستخدم
        sent_user = False
        if user_id:
            sent_user = send_user_fn(
                user_id, number, text, service, otp, now_str()
            )
            if sent_user:
                self.stats["total_sent_user"] += 1

        # 3. إرسال للجروبات
        sent_count = send_group_fn(number, service, otp)
        if sent_count > 0:
            self.stats["total_sent_group"] += 1

        # 4. تسجيل في الداتابيز
        if app:
            with app.app_context():
                log = OTPLog(
                    otp_code=otp,
                    phone_number=number,
                    service_name=service,
                    country_name=msg.get("country", ""),
                    raw_message=text,
                    message_hash=msg_hash,
                    user_id=user_id,
                    sent_to_telegram=(sent_count > 0),
                    sent_to_user=sent_user,
                )
                db.session.add(log)
                db.session.commit()

        logger.info(
            f"📨 OTP {otp} | {service} | {number} | "
            f"user={'✅' if sent_user else '❌'} | "
            f"groups={'✅' if sent_count else '❌'}"
        )

    # ══════════════════════════════════════════════════════════
    #  إحصائيات
    # ══════════════════════════════════════════════════════════
    def get_stats(self) -> dict:
        uptime = ""
        if self.stats["started_at"]:
            delta = datetime.utcnow() - self.stats["started_at"]
            uptime = f"{delta.days}d {delta.seconds // 3600}h {(delta.seconds // 60) % 60}m"

        return {
            "is_running": self.is_running,
            "uptime": uptime,
            "last_check": self.stats["last_check"] or "Never",
            "total_fetched": self.stats["total_fetched"],
            "total_sent_user": self.stats["total_sent_user"],
            "total_sent_group": self.stats["total_sent_group"],
            "total_duplicates": self.stats["total_duplicates"],
            "total_errors": self.stats["total_errors"],
        }

    def check_manually(self) -> str:
        """فحص يدوي من لوحة التحكم"""
        if not self.scraper.is_logged_in:
            if not self.scraper.login():
                return "❌ فشل تسجيل الدخول في iVasms"
        try:
            self._check_once()
            return "✅ تم الفحص"
        except Exception as e:
            return f"❌ خطأ: {e}"


# ══════════════════════════════════════════════════════════════
#  نسخة عالمية
# ══════════════════════════════════════════════════════════════
otp_monitor = OTPMonitor()


def start_monitor() -> str:
    return otp_monitor.start()


def stop_monitor() -> str:
    return otp_monitor.stop()


def get_monitor_stats() -> dict:
    return otp_monitor.get_stats()


def check_manually() -> str:
    return otp_monitor.check_manually()