"""
لوحة تحكم الأدمن - كل حاجات الإدارة
بيتنادى عليها من telegram_bot.py عبر handle_admin_callback
"""

import json
import logging

from telebot import types

from config import config
from models import (
    db, User, Combo, ForceSubChannel, OTPLog,
    get_setting, set_setting,
)
from utils import COUNTRY_CODES, clean_number, html_escape

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  مساعدات للوصول لـ bot و db_lock و user_states
# ══════════════════════════════════════════════════════════════
def _get_bot():
    from telegram_bot import bot
    return bot


def _get_lock():
    from telegram_bot import db_lock
    return db_lock


def _get_states():
    from telegram_bot import user_states
    return user_states


def _safe_answer(call, text, alert=False):
    try:
        _get_bot().answer_callback_query(call.id, text, show_alert=alert)
    except Exception:
        pass


def _safe_edit(call, text, markup=None):
    try:
        _get_bot().edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"فشل تعديل: {e}")


def _is_admin(uid):
    return uid in config.ADMIN_IDS


# ══════════════════════════════════════════════════════════════
#  إشعار مستخدم جديد
# ══════════════════════════════════════════════════════════════
def notify_admin_new_user(message):
    bot = _get_bot()
    text = (
        f"🆕 <b>مستخدم جديد</b>\n\n"
        f"🆔: <code>{message.from_user.id}</code>\n"
        f"👤: @{html_escape(message.from_user.username or 'None')}\n"
        f"📛: {html_escape(message.from_user.first_name or '')}"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            bot.send_message(admin_id, text)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  القائمة الرئيسية للأدمن
# ══════════════════════════════════════════════════════════════
def admin_menu() -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    maintenance = get_setting("maintenance", "0") == "1"
    status = "🔴 قيد الصيانة" if maintenance else "🟢 يعمل"
    m.add(types.InlineKeyboardButton(
        f"حالة البوت: {status}", callback_data="toggle_maintenance"
    ))
    m.row(
        types.InlineKeyboardButton("📥 إضافة كومبو", callback_data="admin_add_combo"),
        types.InlineKeyboardButton("🗑️ حذف كومبو", callback_data="admin_del_combo"),
    )
    m.row(
        types.InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="admin_broadcast"),
    )
    m.row(
        types.InlineKeyboardButton("🚫 حظر", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="admin_unban"),
        types.InlineKeyboardButton("👤 معلومات", callback_data="admin_user_info"),
    )
    m.add(types.InlineKeyboardButton("🔗 قنوات الاشتراك", callback_data="admin_force_sub"))
    m.add(types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main"))
    return m


def admin_text() -> str:
    return (
        "<b>❍─── <u>لوحة التحكم</u> ───❍</b>\n\n"
        "<b>⚙️ تحكم كامل في البوت من هنا</b>\n\n"
        "<b>────────────────────</b>"
    )


# ══════════════════════════════════════════════════════════════
#  Router موحد لكل callbacks الأدمن
# ══════════════════════════════════════════════════════════════
def handle_admin_callback(call) -> bool:
    """يرجع True لو اتعامل مع الـ callback، False لو مش بتاعه"""
    data = call.data or ""

    if data == "admin_panel":
        _cb_admin_panel(call); return True
    if data == "toggle_maintenance":
        _cb_toggle_maintenance(call); return True
    if data == "admin_stats":
        _cb_admin_stats(call); return True
    if data == "admin_add_combo":
        _cb_add_combo(call); return True
    if data == "admin_del_combo":
        _cb_del_combo(call); return True
    if data.startswith("del_combo_"):
        _cb_confirm_del_combo(call); return True
    if data == "admin_ban":
        _cb_admin_ban(call); return True
    if data == "admin_unban":
        _cb_admin_unban(call); return True
    if data == "admin_user_info":
        _cb_admin_user_info(call); return True
    if data == "admin_broadcast":
        _cb_broadcast(call); return True
    if data == "admin_force_sub":
        _cb_admin_force_sub(call); return True
    if data == "ch_add":
        _cb_ch_add(call); return True
    if data.startswith("ch_manage_"):
        _cb_ch_manage(call); return True
    if data.startswith("ch_toggle_"):
        _cb_ch_toggle(call); return True
    if data.startswith("ch_del_"):
        _cb_ch_del(call); return True
    if data.startswith("ch_edit_"):
        _cb_ch_edit(call); return True
    return False


# ══════════════════════════════════════════════════════════════
#  لوحة التحكم
# ══════════════════════════════════════════════════════════════
def _cb_admin_panel(call):
    if not _is_admin(call.from_user.id):
        _safe_answer(call, "⚠️ للأدمن فقط.", alert=True)
        return
    _safe_edit(call, admin_text(), admin_menu())


def _cb_toggle_maintenance(call):
    if not _is_admin(call.from_user.id):
        return
    current = get_setting("maintenance", "0")
    new_val = "0" if current == "1" else "1"
    with _get_lock():
        set_setting("maintenance", new_val)
    msg = "🔓 تم فتح البوت" if new_val == "0" else "🔒 تم قفل البوت"
    _safe_answer(call, msg, alert=True)
    _safe_edit(call, admin_text(), admin_menu())


# ══════════════════════════════════════════════════════════════
#  إحصائيات
# ══════════════════════════════════════════════════════════════
def _cb_admin_stats(call):
    if not _is_admin(call.from_user.id):
        return
    with _get_lock():
        total_users = db.session.query(User).count()
        banned = db.session.query(User).filter_by(is_banned=True).count()
        total_combos = db.session.query(Combo).count()
        total_otps = db.session.query(OTPLog).count()
    text = (
        f"<b>📊 إحصائيات البوت</b>\n\n"
        f"👥 المستخدمين: <b>{total_users}</b>\n"
        f"🚫 المحظورين: <b>{banned}</b>\n"
        f"📦 الكومبوهات: <b>{total_combos}</b>\n"
        f"🔑 OTPs: <b>{total_otps}</b>"
    )
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, text, m)


# ══════════════════════════════════════════════════════════════
#  إضافة كومبو
# ══════════════════════════════════════════════════════════════
def _cb_add_combo(call):
    if not _is_admin(call.from_user.id):
        return
    states = _get_states()
    states[call.from_user.id] = "waiting_combo_file"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, "📤 أرسل ملف TXT فيه الأرقام (سطر لكل رقم)", m)


def handle_combo_document(message) -> bool:
    """يتنادى من register_admin_handlers"""
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    if states.get(message.from_user.id) != "waiting_combo_file":
        return False

    bot = _get_bot()
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        content = downloaded.decode("utf-8", errors="ignore")
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]

        if not lines:
            bot.reply_to(message, "❌ الملف فاضي!")
            states.pop(message.from_user.id, None)
            return True

        first = clean_number(lines[0])
        country_code = None
        for code in sorted(COUNTRY_CODES.keys(), key=len, reverse=True):
            if first.startswith(code):
                country_code = code
                break

        if not country_code:
            bot.reply_to(message, "❌ مش قادر أحدد الدولة!")
            states.pop(message.from_user.id, None)
            return True

        with _get_lock():
            last = db.session.query(Combo).filter_by(
                country_code=country_code, is_private=False
            ).order_by(Combo.combo_index.desc()).first()
            next_idx = (last.combo_index + 1) if last else 1

            combo = Combo(
                country_code=country_code,
                combo_index=next_idx,
                numbers_json=json.dumps(lines, ensure_ascii=False),
                is_private=False,
            )
            db.session.add(combo)
            db.session.commit()

        name, flag = COUNTRY_CODES[country_code]
        bot.reply_to(
            message,
            f"✅ تم حفظ الكومبو\n\n"
            f"🌍 الدولة: {flag} {name}\n"
            f"📦 Combo: #{next_idx}\n"
            f"🔢 عدد الأرقام: {len(lines)}",
        )
        states.pop(message.from_user.id, None)
        return True
    except Exception as e:
        logger.error(f"خطأ في رفع الكومبو: {e}")
        bot.reply_to(message, f"❌ خطأ: {e}")
        states.pop(message.from_user.id, None)
        return True


# ══════════════════════════════════════════════════════════════
#  حذف كومبو
# ══════════════════════════════════════════════════════════════
def _cb_del_combo(call):
    if not _is_admin(call.from_user.id):
        return
    with _get_lock():
        combos = db.session.query(Combo).filter_by(is_private=False).all()

    if not combos:
        _safe_answer(call, "لا توجد كومبوهات!", alert=True)
        return

    m = types.InlineKeyboardMarkup()
    for combo in combos:
        if combo.country_code in COUNTRY_CODES:
            name, flag = COUNTRY_CODES[combo.country_code]
            label = f"🗑️ {flag} {name} (#{combo.combo_index})"
            m.add(types.InlineKeyboardButton(label, callback_data=f"del_combo_{combo.id}"))
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, "اختر الكومبو للحذف:", m)


def _cb_confirm_del_combo(call):
    if not _is_admin(call.from_user.id):
        return
    try:
        combo_id = int(call.data.split("_")[2])
        with _get_lock():
            combo = db.session.query(Combo).filter_by(id=combo_id).first()
            if combo:
                db.session.delete(combo)
                db.session.commit()
                _safe_answer(call, "✅ تم الحذف", alert=True)
            else:
                _safe_answer(call, "❌ غير موجود", alert=True)
    except Exception as e:
        logger.error(f"خطأ في حذف الكومبو: {e}")
        _safe_answer(call, "❌ خطأ", alert=True)
    _cb_del_combo(call)


# ══════════════════════════════════════════════════════════════
#  حظر / فك حظر / معلومات
# ══════════════════════════════════════════════════════════════
def _cb_admin_ban(call):
    if not _is_admin(call.from_user.id):
        return
    states = _get_states()
    states[call.from_user.id] = "ban_user"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, "أرسل ID المستخدم للحظر:", m)


def handle_ban_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    if states.get(message.from_user.id) != "ban_user":
        return False
    bot = _get_bot()
    try:
        uid = int(message.text.strip())
        with _get_lock():
            user = db.session.query(User).filter_by(user_id=uid).first()
            if not user:
                bot.reply_to(message, "❌ المستخدم غير موجود!")
                states.pop(message.from_user.id, None)
                return True
            user.is_banned = True
            db.session.commit()
        bot.reply_to(message, f"✅ تم حظر {uid}")
        states.pop(message.from_user.id, None)
        return True
    except ValueError:
        bot.reply_to(message, "❌ ID غير صالح")
        return True


def _cb_admin_unban(call):
    if not _is_admin(call.from_user.id):
        return
    states = _get_states()
    states[call.from_user.id] = "unban_user"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, "أرسل ID المستخدم لفك الحظر:", m)


def handle_unban_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    if states.get(message.from_user.id) != "unban_user":
        return False
    bot = _get_bot()
    try:
        uid = int(message.text.strip())
        with _get_lock():
            user = db.session.query(User).filter_by(user_id=uid).first()
            if not user:
                bot.reply_to(message, "❌ المستخدم غير موجود!")
                states.pop(message.from_user.id, None)
                return True
            user.is_banned = False
            db.session.commit()
        bot.reply_to(message, f"✅ تم فك حظر {uid}")
        states.pop(message.from_user.id, None)
        return True
    except ValueError:
        bot.reply_to(message, "❌ ID غير صالح")
        return True


def _cb_admin_user_info(call):
    if not _is_admin(call.from_user.id):
        return
    states = _get_states()
    states[call.from_user.id] = "user_info"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, "أرسل ID المستخدم:", m)


def handle_user_info_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    if states.get(message.from_user.id) != "user_info":
        return False
    bot = _get_bot()
    try:
        uid = int(message.text.strip())
        with _get_lock():
            user = db.session.query(User).filter_by(user_id=uid).first()
        if not user:
            bot.reply_to(message, "❌ المستخدم غير موجود!")
            states.pop(message.from_user.id, None)
            return True
        text = (
            f"👤 <b>معلومات المستخدم</b>\n\n"
            f"🆔: <code>{user.user_id}</code>\n"
            f"👤: @{html_escape(user.username or 'None')}\n"
            f"📛: {html_escape(user.first_name or '')} {html_escape(user.last_name or '')}\n"
            f"🌍 الدولة: {html_escape(user.country_code or 'N/A')}\n"
            f"📞 الرقم: {html_escape(user.assigned_number or 'N/A')}\n"
            f"🚫 محظور: {'نعم' if user.is_banned else 'لا'}"
        )
        bot.reply_to(message, text)
        states.pop(message.from_user.id, None)
        return True
    except ValueError:
        bot.reply_to(message, "❌ ID غير صالح")
        return True


# ══════════════════════════════════════════════════════════════
#  الإذاعة
# ══════════════════════════════════════════════════════════════
def _cb_broadcast(call):
    if not _is_admin(call.from_user.id):
        return
    states = _get_states()
    states[call.from_user.id] = "broadcast_msg"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, "أرسل الرسالة اللي عايز تبعتها للجميع:", m)


def handle_broadcast_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    if states.get(message.from_user.id) != "broadcast_msg":
        return False
    bot = _get_bot()
    with _get_lock():
        users = [u.user_id for u in db.session.query(User).filter_by(is_banned=False).all()]

    sent = 0
    failed = 0
    for uid in users:
        try:
            bot.send_message(uid, message.text)
            sent += 1
        except Exception:
            failed += 1
    bot.reply_to(message, f"✅ تم الإرسال لـ {sent}\n❌ فشل: {failed}")
    states.pop(message.from_user.id, None)
    return True


# ══════════════════════════════════════════════════════════════
#  قنوات الاشتراك
# ══════════════════════════════════════════════════════════════
def _cb_admin_force_sub(call):
    if not _is_admin(call.from_user.id):
        return
    with _get_lock():
        channels = db.session.query(ForceSubChannel).all()

    text = "<b>🔗 قنوات الاشتراك الإجباري</b>\n\n"
    if not channels:
        text += "لا توجد قنوات مضافة.\n"
    else:
        for ch in channels:
            status = "✅" if ch.enabled else "❌"
            text += f"{status} {html_escape(ch.channel_url)}\n"

    m = types.InlineKeyboardMarkup()
    for ch in channels:
        m.add(types.InlineKeyboardButton(
            f"🔧 إدارة {ch.channel_url[:30]}",
            callback_data=f"ch_manage_{ch.id}",
        ))
    m.add(types.InlineKeyboardButton("➕ إضافة قناة", callback_data="ch_add"))
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    _safe_edit(call, text, m)


def _cb_ch_add(call):
    if not _is_admin(call.from_user.id):
        return
    states = _get_states()
    states[call.from_user.id] = "ch_add_url"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_force_sub"))
    _safe_edit(call, "أرسل رابط القناة (مثلاً: https://t.me/xxx أو @xxx):", m)


def handle_ch_add_url_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    if states.get(message.from_user.id) != "ch_add_url":
        return False
    bot = _get_bot()
    url = message.text.strip()
    if not (url.startswith("@") or url.startswith("https://t.me/")):
        bot.reply_to(message, "❌ رابط غير صالح!")
        return True
    states[message.from_user.id] = {"step": "ch_add_desc", "url": url}
    bot.reply_to(message, "أرسل وصف القناة (أو اتركه فاضي):")
    return True


def handle_ch_add_desc_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    state = states.get(message.from_user.id)
    if not isinstance(state, dict) or state.get("step") != "ch_add_desc":
        return False

    bot = _get_bot()
    url = state["url"]
    desc = message.text.strip()

    with _get_lock():
        exists = db.session.query(ForceSubChannel).filter_by(channel_url=url).first()
        if exists:
            bot.reply_to(message, "❌ القناة موجودة بالفعل!")
        else:
            ch = ForceSubChannel(channel_url=url, description=desc, enabled=True)
            db.session.add(ch)
            db.session.commit()
            bot.reply_to(message, f"✅ تم إضافة القناة:\n{url}")

    states.pop(message.from_user.id, None)
    return True


def _cb_ch_manage(call):
    if not _is_admin(call.from_user.id):
        return
    try:
        ch_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        return

    with _get_lock():
        ch = db.session.query(ForceSubChannel).filter_by(id=ch_id).first()
    if not ch:
        _safe_answer(call, "❌ غير موجودة", alert=True)
        return

    status = "مفعلة ✅" if ch.enabled else "معطلة ❌"
    text = (
        f"<b>🔧 إدارة القناة</b>\n\n"
        f"🔗 الرابط: {html_escape(ch.channel_url)}\n"
        f"📝 الوصف: {html_escape(ch.description or '—')}\n"
        f"📊 الحالة: {status}"
    )
    m = types.InlineKeyboardMarkup()
    toggle_label = "❌ تعطيل" if ch.enabled else "✅ تفعيل"
    m.add(types.InlineKeyboardButton(toggle_label, callback_data=f"ch_toggle_{ch.id}"))
    m.add(types.InlineKeyboardButton("✏️ تعديل الوصف", callback_data=f"ch_edit_{ch.id}"))
    m.add(types.InlineKeyboardButton("🗑️ حذف", callback_data=f"ch_del_{ch.id}"))
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_force_sub"))
    _safe_edit(call, text, m)


def _cb_ch_toggle(call):
    if not _is_admin(call.from_user.id):
        return
    try:
        ch_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        return
    with _get_lock():
        ch = db.session.query(ForceSubChannel).filter_by(id=ch_id).first()
        if ch:
            ch.enabled = not ch.enabled
            db.session.commit()
    _safe_answer(call, "✅ تم التغيير", alert=True)
    _cb_ch_manage(call)


def _cb_ch_del(call):
    if not _is_admin(call.from_user.id):
        return
    try:
        ch_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        return
    with _get_lock():
        ch = db.session.query(ForceSubChannel).filter_by(id=ch_id).first()
        if ch:
            db.session.delete(ch)
            db.session.commit()
    _safe_answer(call, "🗑️ تم الحذف", alert=True)
    _cb_admin_force_sub(call)


def _cb_ch_edit(call):
    if not _is_admin(call.from_user.id):
        return
    try:
        ch_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        return
    states = _get_states()
    states[call.from_user.id] = f"ch_edit_desc_{ch_id}"
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"ch_manage_{ch_id}"))
    _safe_edit(call, "أرسل الوصف الجديد:", m)


def handle_ch_edit_desc_message(message) -> bool:
    states = _get_states()
    if not _is_admin(message.from_user.id):
        return False
    state = states.get(message.from_user.id)
    if not isinstance(state, str) or not state.startswith("ch_edit_desc_"):
        return False
    bot = _get_bot()
    try:
        ch_id = int(state.split("_")[3])
        desc = message.text.strip()
        with _get_lock():
            ch = db.session.query(ForceSubChannel).filter_by(id=ch_id).first()
            if ch:
                ch.description = desc
                db.session.commit()
        bot.reply_to(message, "✅ تم تحديث الوصف")
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: {e}")
    states.pop(message.from_user.id, None)
    return True


# ══════════════════════════════════════════════════════════════
#  تسجيل Message Handlers
#  لازم تتنادى مرة واحدة في telegram_bot بعد تعريف bot
# ══════════════════════════════════════════════════════════════
def register_admin_handlers():
    """يتنادى مرة واحدة من telegram_bot"""
    bot = _get_bot()

    @bot.message_handler(content_types=["document"])
    def _doc_handler(message):
        handle_combo_document(message)

    @bot.message_handler(func=lambda m: _get_states().get(m.from_user.id) == "ban_user")
    def _ban_handler(message):
        handle_ban_message(message)

    @bot.message_handler(func=lambda m: _get_states().get(m.from_user.id) == "unban_user")
    def _unban_handler(message):
        handle_unban_message(message)

    @bot.message_handler(func=lambda m: _get_states().get(m.from_user.id) == "user_info")
    def _info_handler(message):
        handle_user_info_message(message)

    @bot.message_handler(func=lambda m: _get_states().get(m.from_user.id) == "broadcast_msg")
    def _bc_handler(message):
        handle_broadcast_message(message)

    @bot.message_handler(func=lambda m: _get_states().get(m.from_user.id) == "ch_add_url")
    def _ch_url_handler(message):
        handle_ch_add_url_message(message)

    @bot.message_handler(
        func=lambda m: isinstance(_get_states().get(m.from_user.id), dict)
        and _get_states()[m.from_user.id].get("step") == "ch_add_desc"
    )
    def _ch_desc_handler(message):
        handle_ch_add_desc_message(message)

    @bot.message_handler(
        func=lambda m: isinstance(_get_states().get(m.from_user.id), str)
        and _get_states()[m.from_user.id].startswith("ch_edit_desc_")
    )
    def _ch_edit_handler(message):
        handle_ch_edit_desc_message(message)

    logger.info("✅ Admin message handlers registered")