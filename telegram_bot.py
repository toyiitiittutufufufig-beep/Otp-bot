"""
Telegram Bot - الجزء الأساسي (المستخدم + إرسال OTP)
لوحة الأدمن في admin_panel.py
"""
import time
import json
import random
import logging
import threading
from datetime import datetime

import telebot
from telebot import types

from config import config
from models import db, User, Combo, OTPLog, ForceSubChannel, get_setting
from utils import (
    COUNTRY_CODES, clean_number, html_escape,
    format_otp_for_user, format_otp_for_group,
)

logger = logging.getLogger(__name__)

bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML")
user_states: dict = {}
db_lock = threading.RLock()


# ══════════════════════════════════════════════════════════════
#  مساعدات عامة
# ══════════════════════════════════════════════════════════════
def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def is_banned(user_id: int) -> bool:
    with db_lock:
        user = db.session.query(User).filter_by(user_id=user_id).first()
        return bool(user and user.is_banned)


def get_or_create_user(message) -> User:
    uid = message.from_user.id
    with db_lock:
        user = db.session.query(User).filter_by(user_id=uid).first()
        if not user:
            user = User(
                user_id=uid,
                username=message.from_user.username or "",
                first_name=message.from_user.first_name or "",
                last_name=message.from_user.last_name or "",
            )
            db.session.add(user)
            db.session.commit()
            user._is_new = True
        else:
            user.username = message.from_user.username or user.username
            user.first_name = message.from_user.first_name or user.first_name
            user.last_name = message.from_user.last_name or user.last_name
            user.last_seen = datetime.utcnow()
            db.session.commit()
            user._is_new = False
        return user


def safe_answer(call, text: str, alert: bool = False):
    try:
        bot.answer_callback_query(call.id, text, show_alert=alert)
    except Exception:
        pass


def safe_edit(call, text: str, markup=None):
    try:
        bot.edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"فشل تعديل الرسالة: {e}")


# ══════════════════════════════════════════════════════════════
#  الاشتراك الإجباري
# ══════════════════════════════════════════════════════════════
def get_active_channels() -> list:
    with db_lock:
        return db.session.query(ForceSubChannel).filter_by(enabled=True).all()


def force_sub_check(user_id: int) -> bool:
    channels = get_active_channels()
    if not channels:
        return True
    for ch in channels:
        try:
            url = ch.channel_url.strip()
            if url.startswith("https://t.me/"):
                chat_ref = "@" + url.rstrip("/").split("/")[-1]
            elif url.startswith("@"):
                chat_ref = url
            else:
                continue
            try:
                bot_member = bot.get_chat_member(chat_ref, bot.get_me().id)
                if bot_member.status not in ("administrator", "creator", "member"):
                    continue
            except Exception:
                continue
            member = bot.get_chat_member(chat_ref, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception as e:
            logger.warning(f"خطأ في التحقق من {ch.channel_url}: {e}")
            continue
    return True


def force_sub_markup() -> types.InlineKeyboardMarkup | None:
    channels = get_active_channels()
    if not channels:
        return None
    markup = types.InlineKeyboardMarkup()
    for ch in channels:
        text = f"📢 {ch.description}" if ch.description else "📢 اشترك في القناة"
        markup.add(types.InlineKeyboardButton(text, url=ch.channel_url))
    markup.add(types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub"))
    return markup


# ══════════════════════════════════════════════════════════════
#  بناء القوائم
# ══════════════════════════════════════════════════════════════
def build_main_menu(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    with db_lock:
        user = db.session.query(User).filter_by(user_id=user_id).first()
        private_country = user.private_combo_country if user else None
        combos = db.session.query(Combo).filter_by(is_private=False).all()

    country_map: dict = {}
    for combo in combos:
        country_map.setdefault(combo.country_code, []).append(combo.combo_index)

    if private_country and private_country in COUNTRY_CODES:
        name, flag = COUNTRY_CODES[private_country]
        buttons.append(types.InlineKeyboardButton(
            f"{flag} {name} ⭐", callback_data=f"country_{private_country}_1"
        ))

    for code, indices in country_map.items():
        if code == private_country or code not in COUNTRY_CODES:
            continue
        name, flag = COUNTRY_CODES[code]
        for idx in indices:
            label = f"{flag} {name}" if len(indices) == 1 else f"{flag} {name} ({idx})"
            buttons.append(types.InlineKeyboardButton(label, callback_data=f"country_{code}_{idx}"))

    for i in range(0, len(buttons), 2):
        markup.row(*buttons[i:i + 2])

    if is_admin(user_id):
        markup.add(types.InlineKeyboardButton("🔐 لوحة التحكم", callback_data="admin_panel"))
    return markup


def welcome_text(first_name: str = "") -> str:
    name = html_escape(first_name) if first_name else "صديقي"
    return (
        f"<b>❍─── <u>24XRAVEN SMS BOT</u> ───❍</b>\n\n"
        f"👋 أهلاً <b>{name}</b>!\n\n"
        f"🏴‍☠️ <b>Fast • Secure • Online</b>\n\n"
        f"<b>────────────────────</b>\n"
        f"<b>اختر الدولة اللي عايز رقم منها ⬇️</b>"
    )


def countries_menu_text() -> str:
    return (
        "<b>❍─── <u>اختر الدولة</u> ───❍</b>\n\n"
        "<b>👇 اضغط على الدولة اللي عايز رقم منها</b>"
    )


def back_markup() -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main"))
    return m


# ══════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(message):
    try:
        uid = message.from_user.id
        if get_setting("maintenance", "0") == "1" and not is_admin(uid):
            bot.send_message(message.chat.id, "<b>⚠️ البوت في وضع الصيانة حالياً</b>")
            return
        if is_banned(uid):
            bot.send_message(message.chat.id, "<b>🚫 أنت محظور.</b>")
            return
        if not force_sub_check(uid):
            markup = force_sub_markup()
            if markup:
                bot.send_message(message.chat.id, "<b>🔒 اشترك في القنوات الأول</b>", reply_markup=markup)
            return
        user = get_or_create_user(message)
        if getattr(user, "_is_new", False):
            notify_new_user(message)
        bot.send_message(
            message.chat.id,
            welcome_text(message.from_user.first_name),
            reply_markup=build_main_menu(uid),
        )
    except Exception as e:
        logger.error(f"خطأ في /start: {e}")


def notify_new_user(message):
    from admin_panel import notify_admin_new_user
    notify_admin_new_user(message)


@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def cb_check_sub(call):
    if force_sub_check(call.from_user.id):
        safe_answer(call, "✅ تم التحقق!", alert=True)
        cmd_start(call.message)
    else:
        safe_answer(call, "❌ لم تشترك بعد!", alert=True)


# ══════════════════════════════════════════════════════════════
#  اختيار دولة
# ══════════════════════════════════════════════════════════════
def get_available_numbers(country_code: str, combo_index: int, user_id: int) -> list:
    with db_lock:
        user = db.session.query(User).filter_by(user_id=user_id).first()
        combo = None
        if user and user.private_combo_country == country_code:
            combo = db.session.query(Combo).filter_by(
                country_code=country_code, is_private=True, owner_user_id=user_id
            ).first()
        if not combo:
            combo = db.session.query(Combo).filter_by(
                country_code=country_code, combo_index=combo_index, is_private=False
            ).first()
        if not combo:
            return []
        try:
            all_numbers = json.loads(combo.numbers_json)
        except Exception:
            return []
        used = {
            row[0] for row in db.session.query(User.assigned_number)
            .filter(User.assigned_number.isnot(None), User.assigned_number != "")
            .filter(User.user_id != user_id)
            .all()
        }
        return [n for n in all_numbers if n not in used]


def assign_number(user_id: int, country_code: str, number: str):
    with db_lock:
        user = db.session.query(User).filter_by(user_id=user_id).first()
        if user:
            user.assigned_number = number
            user.country_code = country_code
            db.session.commit()


def show_assigned_number(call, country_code: str, combo_index: int, number: str):
    name, flag = COUNTRY_CODES.get(country_code, ("Unknown", "🌍"))
    text = (
        f"<b>◈ Number:</b> <code>+{html_escape(number)}</code>\n"
        f"<b>◈ Country:</b> {flag} {html_escape(name)}\n"
        f"<b>◈ Combo:</b> #{combo_index}\n"
        f"<b>◈ Status:</b> ⏳ Waiting for SMS"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👀 عرض الـ OTPs", url="https://t.me/Free_Numberv1"))
    markup.row(
        types.InlineKeyboardButton("🔄 تغيير الرقم", callback_data=f"change_{country_code}_{combo_index}"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"),
    )
    safe_edit(call, text, markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("country_"))
def cb_country(call):
    try:
        uid = call.from_user.id
        if is_banned(uid):
            safe_answer(call, "🚫 محظور.", alert=True)
            return
        if not force_sub_check(uid):
            safe_answer(call, "🔒 اشترك الأول.", alert=True)
            return
        parts = call.data.split("_")
        country_code = parts[1]
        combo_index = int(parts[2]) if len(parts) > 2 else 1
        if country_code not in COUNTRY_CODES:
            safe_answer(call, "❌ دولة غير معروفة.", alert=True)
            return
        available = get_available_numbers(country_code, combo_index, uid)
        if not available:
            safe_edit(call, "<b>❌ لا توجد أرقام متاحة.</b>", back_markup())
            return
        new_number = random.choice(available)
        assign_number(uid, country_code, new_number)
        show_assigned_number(call, country_code, combo_index, new_number)
        safe_answer(call, "✅ تم استلام رقم")
    except Exception as e:
        logger.error(f"خطأ في cb_country: {e}")
        safe_answer(call, "❌ حدث خطأ", alert=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith("change_"))
def cb_change_number(call):
    try:
        uid = call.from_user.id
        if is_banned(uid) or not force_sub_check(uid):
            safe_answer(call, "🚫 لا يمكنك.", alert=True)
            return
        parts = call.data.split("_")
        country_code = parts[1]
        combo_index = int(parts[2]) if len(parts) > 2 else 1
        available = get_available_numbers(country_code, combo_index, uid)
        if not available:
            safe_answer(call, "❌ لا توجد أرقام.", alert=True)
            return
        new_number = random.choice(available)
        assign_number(uid, country_code, new_number)
        show_assigned_number(call, country_code, combo_index, new_number)
        safe_answer(call, "✅ تم التغيير")
    except Exception as e:
        logger.error(f"خطأ في cb_change_number: {e}")
        safe_answer(call, "❌ حدث خطأ", alert=True)


@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def cb_back_main(call):
    safe_edit(call, countries_menu_text(), build_main_menu(call.from_user.id))


# ══════════════════════════════════════════════════════════════
#  إرسال OTP
# ══════════════════════════════════════════════════════════════
def send_otp_to_user(user_id: int, number: str, text: str, service: str, otp: str, time_str: str) -> bool:
    try:
        msg = format_otp_for_user(number, text, service, otp, time_str)
        m = types.InlineKeyboardMarkup()
        m.row(
            types.InlineKeyboardButton("👤 Owner", url="https://t.me/H4H_M4"),
            types.InlineKeyboardButton("📢 Channel", url="https://t.me/Raven_xx24"),
        )
        bot.send_message(user_id, msg, reply_markup=m)
        return True
    except Exception as e:
        logger.warning(f"فشل إرسال OTP للمستخدم {user_id}: {e}")
        return False


def send_otp_to_groups(number: str, service: str, otp: str) -> int:
    if not config.CHAT_IDS:
        return 0
    text = format_otp_for_group(number, service, otp)
    success = 0
    for chat_id in config.CHAT_IDS:
        try:
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton(f"⚡ {otp}", callback_data=f"copy_{otp}"))
            m.row(
                types.InlineKeyboardButton("📢 Channel", url="https://t.me/Raven_xx24"),
                types.InlineKeyboardButton("🤖 Bot", url="https://t.me/Free_Numberv1bot"),
            )
            bot.send_message(chat_id, text, reply_markup=m)
            success += 1
        except Exception as e:
            logger.warning(f"فشل إرسال للجروب {chat_id}: {e}")
    return success


@bot.callback_query_handler(func=lambda c: c.data.startswith("copy_"))
def cb_copy(call):
    otp = call.data.split("_", 1)[1]
    safe_answer(call, f"✅ الكود: {otp}", alert=True)


@bot.callback_query_handler(func=lambda c: True)
def cb_unknown(call):
    from admin_panel import handle_admin_callback
    if handle_admin_callback(call):
        return
    safe_answer(call, "⚠️ زر غير متاح، جرب /start", alert=True)


# ══════════════════════════════════════════════════════════════
#  تشغيل
# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
#  تشغيل
# ══════════════════════════════════════════════════════════════
def run_bot_polling():
    logger.info("🚀 بدء Telegram Bot polling...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=50)
        except Exception as e:
            logger.error(f"خطأ polling: {e}")
            time.sleep(5)


def start_bot_thread():
    t = threading.Thread(target=run_bot_polling, daemon=True, name="telegram-bot")
    t.start()
    logger.info("✅ Telegram Bot thread started")
    return t


def init_bot():
    """يتنادى من run.py بعد إنشاء الداتابيز"""
    from admin_panel import register_admin_handlers
    register_admin_handlers()
    logger.info("✅ Bot initialized with admin handlers")