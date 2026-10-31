"""
╔══════════════════════════════════════════════════════════════╗
║  Utilities - دوال مساعدة (OTP extraction, HTML escape, ...) ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import html
import hashlib
from datetime import datetime


# ══════════════════════════════════════════════════════════════
#  أكواد الدول
# ══════════════════════════════════════════════════════════════
COUNTRY_CODES = {
    "1": ("USA/Canada", "🇺🇸"),
    "7": ("Russia", "🇷🇺"),
    "20": ("Egypt", "🇪🇬"),
    "27": ("South Africa", "🇿🇦"),
    "30": ("Greece", "🇬🇷"),
    "31": ("Netherlands", "🇳🇱"),
    "32": ("Belgium", "🇧🇪"),
    "33": ("France", "🇫🇷"),
    "34": ("Spain", "🇪🇸"),
    "36": ("Hungary", "🇭🇺"),
    "39": ("Italy", "🇮🇹"),
    "40": ("Romania", "🇷🇴"),
    "41": ("Switzerland", "🇨🇭"),
    "43": ("Austria", "🇦🇹"),
    "44": ("United Kingdom", "🇬🇧"),
    "45": ("Denmark", "🇩🇰"),
    "46": ("Sweden", "🇸🇪"),
    "47": ("Norway", "🇳🇴"),
    "48": ("Poland", "🇵🇱"),
    "49": ("Germany", "🇩🇪"),
    "51": ("Peru", "🇵🇪"),
    "52": ("Mexico", "🇲🇽"),
    "54": ("Argentina", "🇦🇷"),
    "55": ("Brazil", "🇧🇷"),
    "56": ("Chile", "🇨🇱"),
    "57": ("Colombia", "🇨🇴"),
    "58": ("Venezuela", "🇻🇪"),
    "60": ("Malaysia", "🇲🇾"),
    "61": ("Australia", "🇦🇺"),
    "62": ("Indonesia", "🇮🇩"),
    "63": ("Philippines", "🇵🇭"),
    "64": ("New Zealand", "🇳🇿"),
    "65": ("Singapore", "🇸🇬"),
    "66": ("Thailand", "🇹🇭"),
    "81": ("Japan", "🇯🇵"),
    "82": ("South Korea", "🇰🇷"),
    "84": ("Vietnam", "🇻🇳"),
    "86": ("China", "🇨🇳"),
    "90": ("Turkey", "🇹🇷"),
    "91": ("India", "🇮🇳"),
    "92": ("Pakistan", "🇵🇰"),
    "93": ("Afghanistan", "🇦🇫"),
    "94": ("Sri Lanka", "🇱🇰"),
    "95": ("Myanmar", "🇲🇲"),
    "98": ("Iran", "🇮🇷"),
    "212": ("Morocco", "🇲🇦"),
    "213": ("Algeria", "🇩🇿"),
    "216": ("Tunisia", "🇹🇳"),
    "218": ("Libya", "🇱🇾"),
    "234": ("Nigeria", "🇳🇬"),
    "254": ("Kenya", "🇰🇪"),
    "255": ("Tanzania", "🇹🇿"),
    "256": ("Uganda", "🇺🇬"),
    "351": ("Portugal", "🇵🇹"),
    "353": ("Ireland", "🇮🇪"),
    "358": ("Finland", "🇫🇮"),
    "380": ("Ukraine", "🇺🇦"),
    "966": ("Saudi Arabia", "🇸🇦"),
    "971": ("UAE", "🇦🇪"),
    "974": ("Qatar", "🇶🇦"),
    "965": ("Kuwait", "🇰🇼"),
    "962": ("Jordan", "🇯🇴"),
    "961": ("Lebanon", "🇱🇧"),
    "964": ("Iraq", "🇮🇶"),
}


# ══════════════════════════════════════════════════════════════
#  تنظيف الأرقام
# ══════════════════════════════════════════════════════════════
def clean_number(number: str) -> str:
    """يشيل أي حاجة غير الأرقام"""
    if not number:
        return ""
    return re.sub(r"\D", "", str(number))


def get_country_info(number: str) -> tuple:
    """يرجع (name, flag) للرقم"""
    number = clean_number(number)
    # ترتيب تنازلي حسب الطول عشان الكود الأطول يفوز
    for code in sorted(COUNTRY_CODES.keys(), key=len, reverse=True):
        if number.startswith(code):
            return COUNTRY_CODES[code]
    return ("Unknown", "🌍")


def mask_number(number: str) -> str:
    """يخفي جزء من الرقم"""
    number = clean_number(number)
    if len(number) > 8:
        return f"+{number[:4]}•••{number[-3:]}"
    return f"+{number}" if number else "N/A"


# ══════════════════════════════════════════════════════════════
#  استخراج OTP
# ══════════════════════════════════════════════════════════════
OTP_PATTERNS = [
    r"(?:code|رمز|كود|verification|تحقق|otp|pin)[:\s]+(\d{3,8})",
    r"\b(\d{6})\b",
    r"\b(\d{5})\b",
    r"\b(\d{4})\b",
    r"(\d{3})[- ](\d{3,4})",
]


def extract_otp(text: str) -> str:
    """يستخرج كود OTP من النص"""
    if not text:
        return "N/A"
    for pattern in OTP_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if len(match.groups()) > 1:
                return "".join(match.groups())
            return match.group(1).replace(" ", "").replace("-", "")
    return "N/A"


# ══════════════════════════════════════════════════════════════
#  كشف الخدمة
# ══════════════════════════════════════════════════════════════
SERVICE_PATTERNS = {
    "WhatsApp": ["whatsapp", "واتساب"],
    "Facebook": ["facebook", "فيسبوك"],
    "Instagram": ["instagram", "انستقرام", "انستا"],
    "Telegram": ["telegram", "تيليجرام"],
    "Twitter": ["twitter", "تويتر"],
    "Google": ["google", "gmail", "جوجل"],
    "Discord": ["discord", "ديسكورد"],
    "TikTok": ["tiktok", "تيك توك"],
    "Snapchat": ["snapchat", "سناب"],
    "Amazon": ["amazon", "امازون"],
    "Apple": ["apple", "icloud", "ابل"],
    "Microsoft": ["microsoft", "مايكروسوفت"],
    "Netflix": ["netflix", "نتفلكس"],
    "Spotify": ["spotify", "سبوتيفاي"],
    "YouTube": ["youtube", "يوتيوب"],
    "PayPal": ["paypal", "باي بال"],
}


def detect_service(text: str) -> str:
    """يحاول يعرف الخدمة من النص"""
    if not text:
        return "Unknown"
    text_lower = text.lower()
    for service, keywords in SERVICE_PATTERNS.items():
        for kw in keywords:
            if kw in text_lower:
                return service
    return "Unknown"


# ══════════════════════════════════════════════════════════════
#  Hash للرسالة (لمنع التكرار)
# ══════════════════════════════════════════════════════════════
def message_hash(number: str, text: str) -> str:
    """ينشئ hash فريد للرسالة"""
    raw = f"{clean_number(number)}|{(text or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════
#  HTML Escape
# ══════════════════════════════════════════════════════════════
def html_escape(text) -> str:
    """يهرب HTML بأمان"""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


# ══════════════════════════════════════════════════════════════
#  تنسيق الرسائل
# ══════════════════════════════════════════════════════════════
def format_otp_for_user(number: str, text: str, service: str, otp: str, time_str: str) -> str:
    """رسالة OTP للمستخدم"""
    country_name, flag = get_country_info(number)
    return (
        f"✨ <b>24XRAVEN</b> ✨\n\n"
        f"🌍 <b>Country:</b> {html_escape(country_name)} {flag}\n"
        f"⚙️ <b>Service:</b> {html_escape(service)}\n"
        f"☎️ <b>Number:</b> <code>{html_escape(mask_number(number))}</code>\n"
        f"🕒 <b>Time:</b> {html_escape(time_str)}\n\n"
        f"🔐 <b>Code:</b> <code>{html_escape(otp)}</code>"
    )


def format_otp_for_group(number: str, service: str, otp: str) -> str:
    """رسالة قصيرة للجروب"""
    country_name, flag = get_country_info(number)
    return (
        f"╭───────────────╮\n"
        f"│ {flag} {html_escape(service)} {html_escape(mask_number(number))}\n"
        f"╰───────────────╯"
    )


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")