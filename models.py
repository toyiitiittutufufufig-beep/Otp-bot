"""
╔══════════════════════════════════════════════════════════════╗
║  Database Models - كل جداول الداتابيز                       ║
╚══════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


# ══════════════════════════════════════════════════════════════
#  المستخدمين
# ══════════════════════════════════════════════════════════════
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    country_code = db.Column(db.String(10))
    assigned_number = db.Column(db.String(20), index=True)
    private_combo_country = db.Column(db.String(10))
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.user_id} @{self.username}>"


# ══════════════════════════════════════════════════════════════
#  الكومبوهات (مجموعات الأرقام)
# ══════════════════════════════════════════════════════════════
class Combo(db.Model):
    __tablename__ = "combos"

    id = db.Column(db.Integer, primary_key=True)
    country_code = db.Column(db.String(10), nullable=False, index=True)
    combo_index = db.Column(db.Integer, default=1, nullable=False)
    numbers_json = db.Column(db.Text, nullable=False)  # JSON list
    is_private = db.Column(db.Boolean, default=False)
    owner_user_id = db.Column(db.BigInteger)  # لو كومبو خاص
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("country_code", "combo_index", "is_private", "owner_user_id",
                            name="uq_combo"),
    )

    def __repr__(self):
        return f"<Combo {self.country_code}#{self.combo_index}>"


# ══════════════════════════════════════════════════════════════
#  سجل OTPs
# ══════════════════════════════════════════════════════════════
class OTPLog(db.Model):
    __tablename__ = "otp_logs"

    id = db.Column(db.Integer, primary_key=True)
    otp_code = db.Column(db.String(20), nullable=False, index=True)
    phone_number = db.Column(db.String(20), index=True)
    service_name = db.Column(db.String(100))
    country_name = db.Column(db.String(100))
    raw_message = db.Column(db.Text)
    message_hash = db.Column(db.String(64), unique=True, index=True)
    user_id = db.Column(db.BigInteger, index=True)  # المستخدم اللي جاله
    sent_to_telegram = db.Column(db.Boolean, default=False)
    sent_to_user = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<OTPLog {self.otp_code} - {self.service_name}>"


# ══════════════════════════════════════════════════════════════
#  قنوات الاشتراك الإجباري
# ══════════════════════════════════════════════════════════════
class ForceSubChannel(db.Model):
    __tablename__ = "force_sub_channels"

    id = db.Column(db.Integer, primary_key=True)
    channel_url = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.String(255), default="")
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ForceSubChannel {self.channel_url}>"


# ══════════════════════════════════════════════════════════════
#  إعدادات البوت (key-value)
# ══════════════════════════════════════════════════════════════
class BotSetting(db.Model):
    __tablename__ = "bot_settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<BotSetting {self.key}={self.value}>"


# ══════════════════════════════════════════════════════════════
#  إحصائيات
# ══════════════════════════════════════════════════════════════
class BotStats(db.Model):
    __tablename__ = "bot_stats"

    id = db.Column(db.Integer, primary_key=True)
    stat_name = db.Column(db.String(50), unique=True, nullable=False)
    stat_value = db.Column(db.String(255))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<BotStats {self.stat_name}={self.stat_value}>"


# ══════════════════════════════════════════════════════════════
#  دوال مساعدة للتعامل مع الإعدادات
# ══════════════════════════════════════════════════════════════
def get_setting(key: str, default=None):
    row = db.session.query(BotSetting).filter_by(key=key).first()
    return row.value if row else default


def set_setting(key: str, value: str):
    row = db.session.query(BotSetting).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        row = BotSetting(key=key, value=value)
        db.session.add(row)
    db.session.commit()