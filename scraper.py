"""
╔══════════════════════════════════════════════════════════════╗
║  IVASMS Scraper - جلب OTPs من لوحة iVasms                  ║
║  يعتمد على API الداخلي + CSRF token (زي raven_sms_bot)     ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import time
import logging
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import config
from utils import clean_number, extract_otp, detect_service, message_hash

logger = logging.getLogger(__name__)


class IVASMSScraper:
    """جالب OTPs من iVasms مع إدارة جلسة قوية"""

    def __init__(self):
        self.base_url = config.IVASMS_BASE_URL
        self.login_url = config.IVASMS_LOGIN_URL
        self.sms_api = config.IVASMS_SMS_API

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        })

        self.is_logged_in = False
        self.csrf_token = None
        self.last_login_attempt = 0
        self.login_cooldown = 60  # ثانية بين محاولات الدخول

    # ══════════════════════════════════════════════════════════
    #  تسجيل الدخول
    # ══════════════════════════════════════════════════════════
    def login(self) -> bool:
        """تسجيل الدخول إلى iVasms والحصول على CSRF token"""
        now = time.time()
        if now - self.last_login_attempt < self.login_cooldown:
            logger.warning("تسجيل الدخول في فترة تهدئة، انتظر...")
            return False

        self.last_login_attempt = now

        try:
            # 1. جلب صفحة الدخول
            logger.info("جلب صفحة الدخول...")
            resp = self.session.get(self.login_url, timeout=30)
            resp.raise_for_status()

            # 2. استخراج CSRF token
            soup = BeautifulSoup(resp.text, "html.parser")
            token_input = soup.find("input", {"name": "_token"})
            if not token_input:
                logger.error("لم يتم العثور على _token في صفحة الدخول")
                return False

            csrf = token_input.get("value", "")
            if not csrf:
                logger.error("CSRF token فارغ")
                return False

            # 3. إرسال بيانات الدخول
            login_data = {
                "email": config.IVASMS_EMAIL,
                "password": config.IVASMS_PASSWORD,
                "_token": csrf,
            }

            logger.info("إرسال بيانات الدخول...")
            login_resp = self.session.post(
                self.login_url,
                data=login_data,
                timeout=30,
                allow_redirects=True,
            )

            # 4. التحقق من النجاح (لو اتوجهنا بعيد عن login)
            if "login" in login_resp.url.lower():
                logger.error("فشل تسجيل الدخول: ما زلنا في صفحة login")
                return False

            # 5. استخراج CSRF token الجديد من الصفحة بعد الدخول
            dash_soup = BeautifulSoup(login_resp.text, "html.parser")
            csrf_meta = dash_soup.find("meta", {"name": "csrf-token"})
            if csrf_meta:
                self.csrf_token = csrf_meta.get("content")
                logger.info("تم الحصول على CSRF token جديد")
            else:
                logger.warning("لم يتم العثور على csrf-token meta، سنستخدم القديم")
                self.csrf_token = csrf

            self.is_logged_in = True
            logger.info("✅ تسجيل الدخول ناجح")
            return True

        except requests.RequestException as e:
            logger.error(f"خطأ في الشبكة أثناء الدخول: {e}")
            return False
        except Exception as e:
            logger.error(f"خطأ غير متوقع في الدخول: {e}")
            return False

    # ══════════════════════════════════════════════════════════
    #  ضمان الجلسة
    # ══════════════════════════════════════════════════════════
    def _ensure_logged_in(self) -> bool:
        if not self.is_logged_in:
            return self.login()
        return True

    # ══════════════════════════════════════════════════════════
    #  جلب الرسائل
    # ══════════════════════════════════════════════════════════
    def fetch_messages(self) -> list:
        """
        جلب كل رسائل SMS من آخر 24 ساعة.
        ترجع list of dicts فيها: number, text, service, otp, timestamp, hash
        """
        if not self._ensure_logged_in():
            logger.error("فشل ضمان الجلسة، لا يمكن الجلب")
            return []

        if not self.csrf_token:
            logger.error("CSRF token غير متوفر")
            self.is_logged_in = False
            return []

        try:
            today = datetime.utcnow()
            start_date = (today - timedelta(days=1)).strftime("%m/%d/%Y")
            end_date = today.strftime("%m/%d/%Y")

            headers = {
                "Referer": f"{self.base_url}/portal/sms/received",
                "X-Requested-With": "XMLHttpRequest",
            }

            # 1. جلب ملخص الرسائل (مجموعات الدول)
            summary_payload = {
                "from": start_date,
                "to": end_date,
                "_token": self.csrf_token,
            }

            logger.debug(f"جلب ملخص من {start_date} إلى {end_date}")
            summary_resp = self.session.post(
                self.sms_api,
                headers=headers,
                data=summary_payload,
                timeout=20,
            )
            summary_resp.raise_for_status()

            summary_soup = BeautifulSoup(summary_resp.text, "html.parser")
            country_groups = summary_soup.find_all("div", {"class": "pointer"})

            if not country_groups:
                logger.info("لا توجد مجموعات دول متاحة")
                return []

            # 2. استخراج معرفات المجموعات (الدول)
            group_ids = []
            for group in country_groups:
                onclick = group.get("onclick", "")
                match = re.search(r"getDetials\('(.+?)'\)", onclick)
                if match:
                    group_ids.append(match.group(1))

            if not group_ids:
                logger.warning("لم يتم استخراج أي group_id")
                return []

            logger.debug(f"تم العثور على {len(group_ids)} مجموعة دول")

            # 3. جلب الأرقام لكل مجموعة
            numbers_url = urljoin(self.base_url, "portal/sms/received/getsms/number")
            sms_details_url = urljoin(self.base_url, "portal/sms/received/getsms/number/sms")

            all_messages = []

            for group_id in group_ids:
                try:
                    numbers_payload = {
                        "start": start_date,
                        "end": end_date,
                        "range": group_id,
                        "_token": self.csrf_token,
                    }

                    numbers_resp = self.session.post(
                        numbers_url,
                        headers=headers,
                        data=numbers_payload,
                        timeout=20,
                    )
                    numbers_resp.raise_for_status()
                    numbers_soup = BeautifulSoup(numbers_resp.text, "html.parser")

                    number_divs = numbers_soup.select("div[onclick*='getDetialsNumber']")
                    phone_numbers = [div.text.strip() for div in number_divs]

                    if not phone_numbers:
                        continue

                    logger.debug(f"المجموعة {group_id}: {len(phone_numbers)} رقم")

                    for phone in phone_numbers:
                        try:
                            sms_payload = {
                                "start": start_date,
                                "end": end_date,
                                "Number": phone,
                                "Range": group_id,
                                "_token": self.csrf_token,
                            }

                            sms_resp = self.session.post(
                                sms_details_url,
                                headers=headers,
                                data=sms_payload,
                                timeout=20,
                            )
                            sms_resp.raise_for_status()
                            sms_soup = BeautifulSoup(sms_resp.text, "html.parser")

                            sms_cards = sms_soup.find_all("div", class_="card-body")

                            for card in sms_cards:
                                sms_text_p = card.find("p", class_="mb-0")
                                if not sms_text_p:
                                    continue

                                sms_text = sms_text_p.get_text(separator="\n").strip()
                                if not sms_text:
                                    continue

                                clean_phone = clean_number(phone)
                                otp = extract_otp(sms_text)
                                service = detect_service(sms_text)
                                msg_hash = message_hash(clean_phone, sms_text)

                                all_messages.append({
                                    "number": clean_phone,
                                    "text": sms_text,
                                    "service": service,
                                    "otp": otp,
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "hash": msg_hash,
                                    "country": group_id.strip(),
                                })

                        except Exception as e:
                            logger.warning(f"خطأ في جلب رسائل الرقم {phone}: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"خطأ في معالجة المجموعة {group_id}: {e}")
                    continue

            logger.info(f"✅ تم جلب {len(all_messages)} رسالة من iVasms")
            return all_messages

        except requests.RequestException as e:
            logger.error(f"خطأ في الشبكة أثناء الجلب: {e}")
            self.is_logged_in = False
            return []
        except Exception as e:
            logger.error(f"خطأ غير متوقع في الجلب: {e}")
            self.is_logged_in = False
            return []

    # ══════════════════════════════════════════════════════════
    #  إعادة تعيين
    # ══════════════════════════════════════════════════════════
    def reset(self):
        """إعادة تعيين الجلسة"""
        self.is_logged_in = False
        self.csrf_token = None
        self.session = requests.Session()
        logger.info("تم إعادة تعيين جلسة iVasms")