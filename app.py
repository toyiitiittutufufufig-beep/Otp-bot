"""
Flask App - لوحة التحكم + API Routes
بيتنادى من run.py
"""

import json
import logging
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from config import config
from models import (
    db, User, Combo, OTPLog, ForceSubChannel,
    get_setting, set_setting,
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """ينشئ Flask app ويربط الداتابيز"""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = config.SESSION_SECRET
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        logger.info("✅ Database tables created")
        if get_setting("maintenance") is None:
            set_setting("maintenance", "0")

    # ══════════════════════════════════════════════════════════
    #  Pages
    # ══════════════════════════════════════════════════════════
    @app.route("/")
    def index():
        return render_template("dashboard.html")

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

    # ══════════════════════════════════════════════════════════
    #  API: Status
    # ══════════════════════════════════════════════════════════
    @app.route("/api/status")
    def api_status():
        try:
            from otp_monitor import get_monitor_stats
            monitor = get_monitor_stats()
        except Exception as e:
            logger.warning(f"مش قادر أجيب إحصائيات المراقبة: {e}")
            monitor = {}

        try:
            with app.app_context():
                total_users = db.session.query(User).count()
                total_banned = db.session.query(User).filter_by(is_banned=True).count()
                total_combos = db.session.query(Combo).count()
                total_otps = db.session.query(OTPLog).count()
                maintenance = get_setting("maintenance", "0") == "1"
        except Exception as e:
            logger.error(f"خطأ في إحصائيات الداتابيز: {e}")
            total_users = total_banned = total_combos = total_otps = 0
            maintenance = False

        return jsonify({
            "monitor": monitor,
            "db": {
                "total_users": total_users,
                "total_banned": total_banned,
                "total_combos": total_combos,
                "total_otps": total_otps,
                "maintenance": maintenance,
            },
            "config": {
                "refresh_interval": config.REFRESH_INTERVAL,
                "cache_expire_minutes": config.CACHE_EXPIRE_MINUTES,
            },
            "time": datetime.utcnow().isoformat(),
        })

    # ══════════════════════════════════════════════════════════
    #  API: Start/Stop/Check
    # ══════════════════════════════════════════════════════════
    @app.route("/api/start", methods=["POST"])
    def api_start():
        try:
            from otp_monitor import start_monitor
            result = start_monitor()
            return jsonify({"success": True, "message": result})
        except Exception as e:
            logger.error(f"خطأ في start: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        try:
            from otp_monitor import stop_monitor
            result = stop_monitor()
            return jsonify({"success": True, "message": result})
        except Exception as e:
            logger.error(f"خطأ في stop: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route("/api/check", methods=["POST"])
    def api_check():
        try:
            from otp_monitor import check_manually
            result = check_manually()
            success = not result.startswith("❌")
            return jsonify({"success": success, "message": result})
        except Exception as e:
            logger.error(f"خطأ في check: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    # ══════════════════════════════════════════════════════════
    #  API: OTP Logs
    # ══════════════════════════════════════════════════════════
    @app.route("/api/logs")
    def api_logs():
        try:
            limit = int(request.args.get("limit", 50))
            limit = min(max(limit, 1), 200)

            with app.app_context():
                logs = (
                    db.session.query(OTPLog)
                    .order_by(OTPLog.created_at.desc())
                    .limit(limit)
                    .all()
                )
                data = [
                    {
                        "id": log.id,
                        "otp": log.otp_code,
                        "number": log.phone_number,
                        "service": log.service_name,
                        "country": log.country_name,
                        "user_id": log.user_id,
                        "sent_to_telegram": log.sent_to_telegram,
                        "sent_to_user": log.sent_to_user,
                        "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else None,
                    }
                    for log in logs
                ]
            return jsonify({"success": True, "logs": data, "count": len(data)})
        except Exception as e:
            logger.error(f"خطأ في logs: {e}")
            return jsonify({"success": False, "logs": [], "error": str(e)}), 500

    # ══════════════════════════════════════════════════════════
    #  API: Users
    # ══════════════════════════════════════════════════════════
    @app.route("/api/users")
    def api_users():
        try:
            limit = int(request.args.get("limit", 100))
            limit = min(max(limit, 1), 500)

            with app.app_context():
                users = (
                    db.session.query(User)
                    .order_by(User.last_seen.desc())
                    .limit(limit)
                    .all()
                )
                data = [
                    {
                        "user_id": u.user_id,
                        "username": u.username,
                        "first_name": u.first_name,
                        "country_code": u.country_code,
                        "assigned_number": u.assigned_number,
                        "is_banned": u.is_banned,
                        "last_seen": u.last_seen.strftime("%Y-%m-%d %H:%M:%S") if u.last_seen else None,
                    }
                    for u in users
                ]
            return jsonify({"success": True, "users": data, "count": len(data)})
        except Exception as e:
            logger.error(f"خطأ في users: {e}")
            return jsonify({"success": False, "users": [], "error": str(e)}), 500

    # ══════════════════════════════════════════════════════════
    #  API: Combos
    # ══════════════════════════════════════════════════════════
    @app.route("/api/combos")
    def api_combos():
        try:
            with app.app_context():
                combos = db.session.query(Combo).all()
                data = []
                for c in combos:
                    try:
                        numbers_count = len(json.loads(c.numbers_json))
                    except Exception:
                        numbers_count = 0
                    data.append({
                        "id": c.id,
                        "country_code": c.country_code,
                        "combo_index": c.combo_index,
                        "is_private": c.is_private,
                        "numbers_count": numbers_count,
                        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None,
                    })
            return jsonify({"success": True, "combos": data, "count": len(data)})
        except Exception as e:
            logger.error(f"خطأ في combos: {e}")
            return jsonify({"success": False, "combos": [], "error": str(e)}), 500

    # ══════════════════════════════════════════════════════════
    #  API: Maintenance
    # ══════════════════════════════════════════════════════════
    @app.route("/api/maintenance", methods=["POST"])
    def api_maintenance():
        try:
            with app.app_context():
                current = get_setting("maintenance", "0")
                new_val = "0" if current == "1" else "1"
                set_setting("maintenance", new_val)
            msg = "🔓 تم فتح البوت" if new_val == "0" else "🔒 تم قفل البوت"
            return jsonify({"success": True, "message": msg, "maintenance": new_val == "1"})
        except Exception as e:
            logger.error(f"خطأ في maintenance: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    # ══════════════════════════════════════════════════════════
    #  API: Force Sub Channels
    # ══════════════════════════════════════════════════════════
    @app.route("/api/channels")
    def api_channels():
        try:
            with app.app_context():
                channels = db.session.query(ForceSubChannel).all()
                data = [
                    {
                        "id": ch.id,
                        "channel_url": ch.channel_url,
                        "description": ch.description,
                        "enabled": ch.enabled,
                    }
                    for ch in channels
                ]
            return jsonify({"success": True, "channels": data, "count": len(data)})
        except Exception as e:
            logger.error(f"خطأ في channels: {e}")
            return jsonify({"success": False, "channels": [], "error": str(e)}), 500

    # ══════════════════════════════════════════════════════════
    #  API: Debug (محمي)
    # ══════════════════════════════════════════════════════════
    @app.route("/api/debug")
    def api_debug():
        if not config.DEBUG:
            return jsonify({"error": "Debug mode is off"}), 403

        import sys as _sys
        try:
            from otp_monitor import otp_monitor
            scraper_status = "logged_in" if otp_monitor.scraper.is_logged_in else "logged_out"
        except Exception:
            scraper_status = "unknown"

        return jsonify({
            "python_version": _sys.version,
            "config": {
                "bot_token_set": bool(config.BOT_TOKEN),
                "admin_ids": config.ADMIN_IDS,
                "chat_ids": config.CHAT_IDS,
                "ivasms_email_set": bool(config.IVASMS_EMAIL),
                "ivasms_password_set": bool(config.IVASMS_PASSWORD),
                "database_url": config.DATABASE_URL.split("@")[-1] if "@" in config.DATABASE_URL else config.DATABASE_URL,
                "debug": config.DEBUG,
            },
            "scraper_status": scraper_status,
            "time": datetime.utcnow().isoformat(),
        })

    # ══════════════════════════════════════════════════════════
    #  Error Handlers
    # ══════════════════════════════════════════════════════════
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"500 error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    return app