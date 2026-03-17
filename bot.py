import asyncio
import calendar
import datetime as dt
import hashlib
import hmac
import html
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import telebot
from aiohttp import web
from telebot import types


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("beauty_studio")


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "barber.db"
MINI_APP_DIR = BASE_DIR / "mini_app"

TOKEN = os.getenv("BOT_TOKEN", "8401783289:AAERE_NN15sLerglNeQ1rhselkhVl_Ss0RU")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1065033031"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://example.com").rstrip("/")
WEBAPP_URL = os.getenv("WEBAPP_URL", f"{PUBLIC_BASE_URL}/mini_app/index.html")
BOT_LINK = os.getenv("BOT_LINK", "")
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT") or os.getenv("PORT") or "8080")
ALLOW_UNSAFE_WEBAPP_DEV = os.getenv("ALLOW_UNSAFE_WEBAPP_DEV", "0") == "1"
BRAND_NAME = os.getenv("BRAND_NAME", "Beauty Studio")
BRAND_SUBTITLE = os.getenv("BRAND_SUBTITLE", "Güzellik Saloni")
BONUS_PER_BOOKING = 2500
FREE_SERVICE_VISITS = 3
VIP_VISITS = 5
VIP_DISCOUNT_PERCENT = 10
REFERRAL_BONUS = 5000
BOOKING_WINDOW_DAYS = 45
PHOTO_URL = os.getenv(
    "HERO_PHOTO_URL",
    "https://images.unsplash.com/photo-1560066984-138dadb4c035"
    "?auto=format&fit=crop&w=1200&q=80",
)

LOCATION = {
    "lat": 41.311081,
    "lon": 69.279737,
    "address": "Toshkent shahri, Amir Temur ko'chasi, 1-uy",
    "schedule": "09:00 — 21:00, har kuni",
    "yandex": "https://yandex.com/maps/?pt=69.279737,41.311081&z=18",
    "two_gis": "https://2gis.uz/tashkent",
}

SERVICES = [
    {
        "id": "classic_manicure",
        "name": "Manikur (klassik)",
        "price": 80000,
        "duration": 60,
        "description": "Toza, nafis va kundalik parvarish uchun klassik manikur.",
    },
    {
        "id": "pedicure",
        "name": "Pedikur",
        "price": 100000,
        "duration": 75,
        "description": "Oyoqlar uchun to'liq parvarish va nozik finish.",
    },
    {
        "id": "brow_design",
        "name": "Qosh dizayni",
        "price": 40000,
        "duration": 30,
        "description": "Yuz tuzilishiga mos chiroyli qosh shakli.",
    },
    {
        "id": "facial_care",
        "name": "Yuz parvarishi (facial)",
        "price": 120000,
        "duration": 90,
        "description": "Terni yangilovchi va namlantiruvchi facial muolajasi.",
    },
    {
        "id": "hair_coloring",
        "name": "Soch bo'yash",
        "price": 200000,
        "duration": 120,
        "description": "Professional rang va yumshoq parvarish bilan bo'yash.",
    },
    {
        "id": "bridal_makeup",
        "name": "Kelin makiyaji",
        "price": 350000,
        "duration": 180,
        "description": "Maxsus kun uchun nafis va uzoq saqlanadigan obraz.",
    },
]

MASTERS = [
    {
        "id": "malika",
        "name": "Malika",
        "title": "Top Stylist",
        "emoji": "💅",
        "about": "Premium manikur va bridal look bo'yicha yetakchi stylist.",
    },
    {
        "id": "zulfiya",
        "name": "Zulfiya",
        "title": "Senior Master",
        "emoji": "💇‍♀️",
        "about": "Soch bo'yash, facial va yumshoq beauty parvarish ustasi.",
    },
    {
        "id": "nodira",
        "name": "Nodira",
        "title": "Master",
        "emoji": "✨",
        "about": "Qosh dizayni, pedikur va nozik finishing bo'yicha ishonchli usta.",
    },
]

TIME_SLOTS = [
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
    "19:00",
    "20:00",
]

MONTHS_UZ = [
    "",
    "Yanvar",
    "Fevral",
    "Mart",
    "Aprel",
    "May",
    "Iyun",
    "Iyul",
    "Avgust",
    "Sentabr",
    "Oktabr",
    "Noyabr",
    "Dekabr",
]
WEEKDAYS_UZ = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]

SERVICE_MAP = {service["id"]: service for service in SERVICES}
MASTER_MAP = {master["id"]: master for master in MASTERS}

db_lock = threading.RLock()
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)


class BookingError(Exception):
    pass


class ValidationError(BookingError):
    pass


class SlotTakenError(BookingError):
    pass


class AuthError(BookingError):
    pass


def format_currency(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""))


def get_today() -> dt.date:
    return dt.date.today()


def get_now() -> dt.datetime:
    return dt.datetime.now()


def remaining_visits_for_free(visits: int) -> int:
    return (FREE_SERVICE_VISITS - (visits % FREE_SERVICE_VISITS)) % FREE_SERVICE_VISITS


def build_ref_code(user_id: int) -> str:
    return f"beauty{user_id}"


def visit_status(visits: int) -> str:
    return "VIP 👑" if visits >= VIP_VISITS else "Mehmon 🌸"


def booking_datetime(date_str: str, time_str: str) -> dt.datetime:
    return dt.datetime.combine(dt.date.fromisoformat(date_str), dt.time.fromisoformat(time_str))


def display_date(date_str: str) -> str:
    try:
        date_value = dt.date.fromisoformat(date_str)
    except ValueError:
        return date_str
    weekday = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
    return f"{date_value.day} {MONTHS_UZ[date_value.month]}, {weekday[date_value.weekday()]}"


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if digits.startswith("998") and not digits.startswith("+998"):
        digits = f"+{digits}"
    if digits and not digits.startswith("+"):
        digits = f"+{digits}"
    return digits


def looks_like_phone(value: str) -> bool:
    digits = "".join(ch for ch in value if ch.isdigit())
    return 9 <= len(digits) <= 15


def safe_delete(chat_id: int, message_id: int) -> None:
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def safe_answer_callback(call_id: str, text: str = "", show_alert: bool = False) -> None:
    try:
        bot.answer_callback_query(call_id, text, show_alert=show_alert)
    except Exception:
        pass


def get_service(service_id: str) -> dict[str, Any]:
    service = SERVICE_MAP.get(service_id)
    if not service:
        raise ValidationError("Tanlangan xizmat topilmadi.")
    return service


def get_master(master_id: str) -> dict[str, Any]:
    master = MASTER_MAP.get(master_id)
    if not master:
        raise ValidationError("Tanlangan master topilmadi.")
    return master


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db() -> None:
    with db_lock:
        conn = get_conn()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    bonus INTEGER DEFAULT 0,
                    visits INTEGER DEFAULT 0,
                    vip_status TEXT DEFAULT 'REGULAR',
                    ref_code TEXT DEFAULT '',
                    referred_by INTEGER,
                    referral_bonus_paid INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS booking_state (
                    user_id INTEGER PRIMARY KEY,
                    source TEXT DEFAULT 'bot',
                    step TEXT DEFAULT '',
                    service_id TEXT DEFAULT '',
                    service_name TEXT DEFAULT '',
                    service_price INTEGER DEFAULT 0,
                    master_id TEXT DEFAULT '',
                    master_name TEXT DEFAULT '',
                    date TEXT DEFAULT '',
                    time TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    name TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    service_id TEXT DEFAULT '',
                    service TEXT NOT NULL DEFAULT '',
                    service_price INTEGER DEFAULT 0,
                    master_id TEXT DEFAULT '',
                    master TEXT NOT NULL DEFAULT '',
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    final_price INTEGER DEFAULT 0,
                    discount_percent INTEGER DEFAULT 0,
                    reminder_sent INTEGER DEFAULT 0,
                    review_request_sent INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    source TEXT NOT NULL DEFAULT 'bot',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
                    text TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            ensure_column(conn, "users", "full_name", "TEXT DEFAULT ''")
            ensure_column(conn, "users", "phone", "TEXT DEFAULT ''")
            ensure_column(conn, "users", "vip_status", "TEXT DEFAULT 'REGULAR'")
            ensure_column(conn, "users", "ref_code", "TEXT DEFAULT ''")
            ensure_column(conn, "users", "referred_by", "INTEGER")
            ensure_column(conn, "users", "referral_bonus_paid", "INTEGER DEFAULT 0")
            ensure_column(conn, "bookings", "service_id", "TEXT DEFAULT ''")
            ensure_column(conn, "bookings", "service_price", "INTEGER DEFAULT 0")
            ensure_column(conn, "bookings", "master_id", "TEXT DEFAULT ''")
            ensure_column(conn, "bookings", "final_price", "INTEGER DEFAULT 0")
            ensure_column(conn, "bookings", "discount_percent", "INTEGER DEFAULT 0")
            ensure_column(conn, "bookings", "reminder_sent", "INTEGER DEFAULT 0")
            ensure_column(conn, "bookings", "review_request_sent", "INTEGER DEFAULT 0")
            ensure_column(conn, "bookings", "source", "TEXT DEFAULT 'bot'")
            ensure_column(conn, "booking_state", "source", "TEXT DEFAULT 'bot'")
            ensure_column(conn, "booking_state", "step", "TEXT DEFAULT ''")
            ensure_column(conn, "booking_state", "service_id", "TEXT DEFAULT ''")
            ensure_column(conn, "booking_state", "service_name", "TEXT DEFAULT ''")
            ensure_column(conn, "booking_state", "service_price", "INTEGER DEFAULT 0")
            ensure_column(conn, "booking_state", "master_id", "TEXT DEFAULT ''")
            ensure_column(conn, "booking_state", "master_name", "TEXT DEFAULT ''")
            ensure_column(conn, "booking_state", "phone", "TEXT DEFAULT ''")
            ensure_column(conn, "booking_state", "name", "TEXT DEFAULT ''")

            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_active_slot_unique
                ON bookings (master, date, time)
                WHERE status = 'active'
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bookings_user_status_date
                ON bookings (user_id, status, date)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_booking_state_updated
                ON booking_state (updated_at)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_ref_code
                ON users (ref_code)
                WHERE ref_code != ''
                """
            )
            conn.commit()
        finally:
            conn.close()


init_db()


def init_user(user_id: int, full_name: str = "", phone: str = "") -> None:
    ref_code = build_ref_code(user_id)
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (user_id, full_name, phone, bonus, visits, ref_code)
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                (user_id, full_name.strip(), phone.strip(), ref_code),
            )
            conn.execute(
                """
                UPDATE users
                SET full_name = CASE WHEN ? != '' THEN ? ELSE full_name END,
                    phone = CASE WHEN ? != '' THEN ? ELSE phone END,
                    ref_code = CASE WHEN ref_code = '' THEN ? ELSE ref_code END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (full_name.strip(), full_name.strip(), phone.strip(), phone.strip(), ref_code, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_user_profile(user_id: int) -> dict[str, Any]:
    with db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                """
                SELECT user_id, full_name, phone, bonus, visits, vip_status, ref_code, referred_by
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if not row:
                return {
                    "user_id": user_id,
                    "full_name": "",
                    "phone": "",
                    "bonus": 0,
                    "visits": 0,
                    "vip_status": "Mehmon 🌸",
                    "ref_code": build_ref_code(user_id),
                    "referred_by": None,
                    "remaining_for_free": FREE_SERVICE_VISITS,
                    "upcoming": [],
                }
            upcoming = conn.execute(
                """
                SELECT id, service, master, date, time
                FROM bookings
                WHERE user_id = ? AND status = 'active' AND date >= ?
                ORDER BY date, time
                LIMIT 5
                """,
                (user_id, get_today().isoformat()),
            ).fetchall()
            result = dict(row)
            result["remaining_for_free"] = remaining_visits_for_free(result["visits"])
            result["vip_status"] = visit_status(result["visits"])
            result["upcoming"] = [dict(item) for item in upcoming]
            return result
        finally:
            conn.close()


def get_state(user_id: int) -> dict[str, Any]:
    with db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM booking_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()


def set_state(user_id: int, **kwargs: Any) -> None:
    allowed_fields = {
        "source",
        "step",
        "service_id",
        "service_name",
        "service_price",
        "master_id",
        "master_name",
        "date",
        "time",
        "phone",
        "name",
    }
    invalid = set(kwargs) - allowed_fields
    if invalid:
        raise ValidationError(f"Noto'g'ri state maydonlari: {', '.join(sorted(invalid))}")

    with db_lock:
        conn = get_conn()
        try:
            conn.execute("INSERT OR IGNORE INTO booking_state (user_id) VALUES (?)", (user_id,))
            for key, value in kwargs.items():
                conn.execute(
                    f"""
                    UPDATE booking_state
                    SET {key} = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """,
                    (value, user_id),
                )
            conn.commit()
        finally:
            conn.close()


def clear_state(user_id: int) -> None:
    with db_lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM booking_state WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()


def store_review(user_id: int, stars: int) -> None:
    with db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO reviews (user_id, stars) VALUES (?, ?)",
                (user_id, stars),
            )
            conn.commit()
        finally:
            conn.close()


def get_review_summary() -> dict[str, Any]:
    with db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total, ROUND(AVG(stars), 1) AS avg_rating
                FROM reviews
                """
            ).fetchone()
            return {
                "total": row["total"] if row and row["total"] else 0,
                "avg_rating": row["avg_rating"] if row and row["avg_rating"] else 0,
            }
        finally:
            conn.close()


def get_taken_slots(master_name: str, date_str: str) -> set[str]:
    with db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT time
                FROM bookings
                WHERE master = ? AND date = ? AND status = 'active'
                """,
                (master_name, date_str),
            ).fetchall()
            return {row["time"] for row in rows}
        finally:
            conn.close()


def validate_date(date_str: str) -> dt.date:
    try:
        date_value = dt.date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValidationError("Sana noto'g'ri formatda.") from exc

    today = get_today()
    max_date = today + dt.timedelta(days=BOOKING_WINDOW_DAYS)
    if date_value < today or date_value > max_date:
        raise ValidationError("Faqat yaqin kunlar uchun bron qilish mumkin.")
    return date_value


def validate_booking_datetime(date_str: str, time_str: str) -> tuple[dt.date, str]:
    date_value = validate_date(date_str)
    if time_str not in TIME_SLOTS:
        raise ValidationError("Vaqt sloti noto'g'ri.")

    booking_time = dt.datetime.combine(date_value, dt.time.fromisoformat(time_str))
    if booking_time <= get_now():
        raise ValidationError("O'tib ketgan vaqtni tanlab bo'lmaydi.")

    return date_value, time_str


def build_confirmation_text(state: dict[str, Any]) -> str:
    return (
        "🌸 <b>Ma'lumotlarni tasdiqlang</b>\n\n"
        f"💗 Xizmat: <b>{html_escape(state.get('service_name', '-'))}</b>\n"
        f"✨ Usta: <b>{html_escape(state.get('master_name', '-'))}</b>\n"
        f"🪷 Sana: <b>{html_escape(display_date(state.get('date', '-')))}</b>\n"
        f"💗 Vaqt: <b>{html_escape(state.get('time', '-'))}</b>\n"
        f"📱 Raqam: <b>{html_escape(state.get('phone', '-'))}</b>"
    )


def build_success_text(result: dict[str, Any]) -> str:
    lines = [
        "🌸 <b>Muvoffaqiyatli!</b>",
        "",
        f"🪷 {html_escape(display_date(result['date']))} soat {html_escape(result['time'])}",
        f"💅 {html_escape(result['service_name'])}",
        f"✨ Usta: {html_escape(result['master_name'])}",
        "",
        f"💗 <b>Bonus +{format_currency(BONUS_PER_BOOKING)} UZS qo'shildi!</b>",
        "👑 <b>VIP mijoz bonusi!</b>",
        f"💰 Umumiy bonus: {format_currency(result['bonus'])} UZS",
    ]
    if result.get("discount_percent"):
        lines.append(f"🌸 VIP chegirma: {result['discount_percent']}%")
        lines.append(f"💵 Yakuniy narx: {format_currency(result['final_price'])} UZS")
    elif result.get("vip_status") == "VIP 👑":
        lines.append("👑 VIP status faollashdi! Keyingi yozilishlarda 10% chegirma ishlaydi.")
    lines.append(f"🪷 Keyingi bepul xizmat: yana {result['remaining_for_free']} tashrif")
    if result.get("referral_awarded"):
        lines.append(f"💗 Referal bonusi: +{format_currency(REFERRAL_BONUS)} UZS")
    return "\n".join(lines)


def send_admin_notification(result: dict[str, Any]) -> None:
    text = (
        "🌸 <b>Yangi yozilish!</b>\n\n"
        f"👤 Mijoz: {html_escape(result['name'])}\n"
        f"📱 Raqam: {html_escape(result['phone'])}\n"
        f"💗 Xizmat: {html_escape(result['service_name'])}\n"
        f"✨ Usta: {html_escape(result['master_name'])}\n"
        f"🪷 Sana: {html_escape(display_date(result['date']))}\n"
        f"💗 Vaqt: {html_escape(result['time'])}\n"
        f"🧾 ID: #{result['booking_id']}\n"
        f"📲 Manba: {html_escape(result['source'])}\n"
        f"👑 Status: {html_escape(result['vip_status'])}"
    )
    try:
        bot.send_message(ADMIN_ID, text)
    except Exception as exc:
        logger.warning("Admin notify error: %s", exc)


def create_booking(
    user_id: int,
    *,
    service_id: str,
    master_id: str,
    date_str: str,
    time_str: str,
    phone: str,
    name: str,
    source: str,
) -> dict[str, Any]:
    service = get_service(service_id)
    master = get_master(master_id)
    validate_booking_datetime(date_str, time_str)

    cleaned_phone = normalize_phone(phone)
    cleaned_name = (name or "").strip()
    if not cleaned_phone:
        raise ValidationError("Telefon raqamini yuboring.")
    if not looks_like_phone(cleaned_phone):
        raise ValidationError("Telefon raqami noto'g'ri.")
    if not cleaned_name:
        cleaned_name = "Mijoz"

    with db_lock:
        conn = get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT OR IGNORE INTO users (user_id, full_name, phone, bonus, visits, ref_code)
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                (user_id, cleaned_name, cleaned_phone, build_ref_code(user_id)),
            )
            user_before = conn.execute(
                """
                SELECT bonus, visits, vip_status, referred_by, referral_bonus_paid
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            current_visits = user_before["visits"] if user_before else 0
            vip_active = current_visits >= VIP_VISITS or (user_before and user_before["vip_status"] == "VIP 👑")
            discount_percent = VIP_DISCOUNT_PERCENT if vip_active else 0
            final_price = int(service["price"] * (100 - discount_percent) / 100)
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, phone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (cleaned_name, cleaned_phone, user_id),
            )
            cursor = conn.execute(
                """
                INSERT INTO bookings (
                    user_id, name, phone, service_id, service, service_price,
                    master_id, master, date, time, final_price, discount_percent, status, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    user_id,
                    cleaned_name,
                    cleaned_phone,
                    service["id"],
                    service["name"],
                    service["price"],
                    master["id"],
                    master["name"],
                    date_str,
                    time_str,
                    final_price,
                    discount_percent,
                    source,
                ),
            )
            new_visits = current_visits + 1
            new_vip_status = visit_status(new_visits)
            conn.execute(
                """
                UPDATE users
                SET bonus = bonus + ?, visits = visits + 1, vip_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (BONUS_PER_BOOKING, new_vip_status, user_id),
            )
            referral_awarded = False
            referrer_id = user_before["referred_by"] if user_before else None
            if referrer_id and user_before["referral_bonus_paid"] == 0 and current_visits == 0:
                conn.execute(
                    "UPDATE users SET bonus = bonus + ? WHERE user_id IN (?, ?)",
                    (REFERRAL_BONUS, user_id, referrer_id),
                )
                conn.execute(
                    "UPDATE users SET referral_bonus_paid = 1 WHERE user_id = ?",
                    (user_id,),
                )
                referral_awarded = True
            user_row = conn.execute(
                "SELECT bonus, visits, vip_status FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise SlotTakenError("Bu vaqt allaqachon band bo'lib qoldi.") from exc
        finally:
            conn.close()

    visits = user_row["visits"] if user_row else 1
    return {
        "booking_id": cursor.lastrowid,
        "user_id": user_id,
        "name": cleaned_name,
        "phone": cleaned_phone,
        "service_id": service["id"],
        "service_name": service["name"],
        "master_id": master["id"],
        "master_name": master["name"],
        "date": date_str,
        "time": time_str,
        "bonus": user_row["bonus"] if user_row else BONUS_PER_BOOKING,
        "visits": visits,
        "remaining_for_free": remaining_visits_for_free(visits),
        "vip_status": user_row["vip_status"] if user_row else visit_status(visits),
        "discount_percent": discount_percent,
        "final_price": final_price,
        "referral_awarded": referral_awarded,
        "referrer_id": referrer_id,
        "source": source,
    }


def cancel_booking_for_user(user_id: int, booking_id: int) -> bool:
    with db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                """
                SELECT id
                FROM bookings
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (booking_id, user_id),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ?",
                (booking_id,),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def cancel_booking_as_admin(booking_id: int) -> bool:
    with db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM bookings WHERE id = ? AND status = 'active'",
                (booking_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ?",
                (booking_id,),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def get_admin_bookings(limit: int = 20) -> list[dict[str, Any]]:
    with db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT id, name, phone, service, master, date, time, source
                FROM bookings
                WHERE date >= ? AND status = 'active'
                ORDER BY date, time
                LIMIT ?
                """,
                (get_today().isoformat(), limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def attach_referrer(user_id: int, referrer_id: int) -> bool:
    if user_id == referrer_id:
        return False

    with db_lock:
        conn = get_conn()
        try:
            init_user(referrer_id)
            row = conn.execute(
                "SELECT referred_by FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row and row["referred_by"]:
                return False
            conn.execute(
                """
                UPDATE users
                SET referred_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (referrer_id, user_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def build_referral_link(user_id: int) -> str:
    if BOT_LINK:
        return f"{BOT_LINK}?start=ref_{user_id}"
    return ""


def notify_referral_bonus(referrer_id: int, user_id: int) -> None:
    try:
        bot.send_message(
            referrer_id,
            f"🌸 Tabriklaymiz! Tavsiyangiz orqali yangi mijoz yozildi.\n\n💗 Sizga +{format_currency(REFERRAL_BONUS)} UZS bonus qo'shildi.",
        )
    except Exception as exc:
        logger.warning("Could not notify referrer: %s", exc)
    try:
        bot.send_message(
            user_id,
            f"💗 Referal bonusi faollashdi!\n\nSizga va do'stingizga +{format_currency(REFERRAL_BONUS)} UZS bonus qo'shildi.",
        )
    except Exception as exc:
        logger.warning("Could not notify referred user: %s", exc)


def request_contact_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row(types.KeyboardButton("💗 Raqamni yuborish", request_contact=True))
    markup.row(types.KeyboardButton("🏠 Asosiy menyu"))
    return markup


def back_keyboard(callback_data: str = "back_main") -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data=callback_data))
    return markup


def main_menu_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("💅 Yozilish", callback_data="booking_start"))
    markup.add(types.InlineKeyboardButton("🚀 Ochiq Mini App", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    markup.add(
        types.InlineKeyboardButton("🌸 Xizmatlar", callback_data="services"),
        types.InlineKeyboardButton("👤 Kabinet", callback_data="cabinet"),
    )
    markup.add(
        types.InlineKeyboardButton("⭐ Sharhlar", callback_data="reviews"),
        types.InlineKeyboardButton("📍 Manzil", callback_data="location"),
    )
    markup.add(types.InlineKeyboardButton("👑 VIP & Bonus", callback_data="vip_bonus"))
    return markup


def services_keyboard(is_booking: bool) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    prefix = "book_service_" if is_booking else "info_service_"
    for service in SERVICES:
        markup.add(
            types.InlineKeyboardButton(
                f"🌸 {service['name']} — {format_currency(service['price'])} UZS",
                callback_data=f"{prefix}{service['id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_main"))
    return markup


def masters_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    for master in MASTERS:
        markup.add(
            types.InlineKeyboardButton(
                f"{master['emoji']} {master['name']} ({master['title']})",
                callback_data=f"book_master_{master['id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="booking_start"))
    return markup


def create_calendar(year: int | None = None, month: int | None = None) -> types.InlineKeyboardMarkup:
    today = get_today()
    start_month = dt.date(today.year, today.month, 1)
    max_month_date = today + dt.timedelta(days=BOOKING_WINDOW_DAYS)
    end_month = dt.date(max_month_date.year, max_month_date.month, 1)

    if year is None or month is None:
        year = today.year
        month = today.month

    current_month = dt.date(year, month, 1)
    markup = types.InlineKeyboardMarkup(row_width=7)
    markup.add(types.InlineKeyboardButton(f"🟡 {MONTHS_UZ[month]} {year}", callback_data="ignore"))
    markup.row(*[types.InlineKeyboardButton(day, callback_data="ignore") for day in WEEKDAYS_UZ])

    for week in calendar.monthcalendar(year, month):
        buttons = []
        for day in week:
            if day == 0:
                buttons.append(types.InlineKeyboardButton(" ", callback_data="ignore"))
                continue
            date_value = dt.date(year, month, day)
            if date_value < today or date_value > max_month_date:
                buttons.append(types.InlineKeyboardButton("✖️", callback_data="ignore"))
            else:
                buttons.append(
                    types.InlineKeyboardButton(
                        str(day),
                        callback_data=f"book_date_{date_value.isoformat()}",
                    )
                )
        markup.row(*buttons)

    prev_month = (current_month.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    next_month = (current_month + dt.timedelta(days=32)).replace(day=1)
    prev_callback = "ignore" if current_month <= start_month else f"cal_{prev_month.year}_{prev_month.month}"
    next_callback = "ignore" if current_month >= end_month else f"cal_{next_month.year}_{next_month.month}"
    markup.row(
        types.InlineKeyboardButton("◀️", callback_data=prev_callback),
        types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_masters"),
        types.InlineKeyboardButton("▶️", callback_data=next_callback),
    )
    return markup


def times_keyboard(master_name: str, date_str: str) -> types.InlineKeyboardMarkup:
    taken = get_taken_slots(master_name, date_str)
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for slot in TIME_SLOTS:
        if slot in taken:
            buttons.append(types.InlineKeyboardButton(f"🔴 {slot}", callback_data="slot_taken"))
        else:
            buttons.append(types.InlineKeyboardButton(f"🟢 {slot}", callback_data=f"book_time_{slot}"))
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_calendar"))
    return markup


def confirm_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="book_confirm"))
    markup.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="back_main"))
    return markup


def booking_actions_keyboard(bookings: list[dict[str, Any]]) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    for booking in bookings:
        markup.add(
            types.InlineKeyboardButton(
                f"❌ Bekor qilish: {booking['date']} {booking['time']} ({booking['master']})",
                callback_data=f"cancel_booking_{booking['id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_main"))
    return markup


def send_main_menu(chat_id: int, user_id: int) -> None:
    init_user(user_id)
    caption = (
        f"🌸 <b>{html_escape(BRAND_NAME)}</b>\n"
        f"<i>{html_escape(BRAND_SUBTITLE)}</i>\n\n"
        "Salom! 🌸 Sizni ko'rganimizdan xursandmiz!\n\n"
        "O'zingizga mos beauty xizmatni tanlang, qulay vaqtni belgilang va bir necha bosqichda yoziling."
    )
    try:
        bot.send_photo(chat_id, PHOTO_URL, caption=caption, reply_markup=main_menu_keyboard())
    except Exception:
        bot.send_message(chat_id, caption, reply_markup=main_menu_keyboard())


def show_services(chat_id: int) -> None:
    lines = ["🌸 <b>Xizmatlar va narxlar</b>\n"]
    for service in SERVICES:
        lines.append(
            f"• <b>{html_escape(service['name'])}</b> — {format_currency(service['price'])} UZS\n"
            f"  ⏱ {service['duration']} daqiqa\n"
            f"  {html_escape(service['description'])}"
        )
    lines.append("\nYoqtirgan xizmatni tanlab, yozilishni davom ettirishingiz mumkin.")
    bot.send_message(chat_id, "\n\n".join(lines), reply_markup=services_keyboard(is_booking=False))


def show_cabinet(chat_id: int, user_id: int) -> None:
    profile = get_user_profile(user_id)
    text = (
        "👤 <b>Shaxsiy kabinet</b>\n\n"
        f"👑 Status: <b>{html_escape(profile['vip_status'])}</b>\n"
        f"💗 Bonus: <b>{format_currency(profile['bonus'])} UZS</b>\n"
        f"🌸 Tashriflar: <b>{profile['visits']}</b>\n"
        f"🪷 Keyingi bepul xizmat: yana <b>{profile['remaining_for_free']}</b> tashrif\n"
    )
    if profile["phone"]:
        text += f"\n📱 Raqam: <b>{html_escape(profile['phone'])}</b>\n"
    if profile["upcoming"]:
        text += "\n🪷 <b>Kelgusi yozilishlar:</b>\n"
        for booking in profile["upcoming"]:
            text += (
                f"▫️ {html_escape(display_date(booking['date']))}, {html_escape(booking['time'])}\n"
                f"   {html_escape(booking['service'])} • {html_escape(booking['master'])}\n"
            )
        markup = booking_actions_keyboard(profile["upcoming"])
    else:
        text += "\n📭 Hozircha faol qabullar yo'q."
        markup = back_keyboard()
    bot.send_message(chat_id, text, reply_markup=markup)


def show_reviews(chat_id: int) -> None:
    summary = get_review_summary()
    markup = types.InlineKeyboardMarkup(row_width=5)
    markup.row(*[
        types.InlineKeyboardButton("⭐" * stars, callback_data=f"review_{stars}")
        for stars in range(1, 6)
    ])
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_main"))
    text = (
        "⭐ <b>Sharhlar</b>\n\n"
        f"O'rtacha baho: <b>{summary['avg_rating']}</b>\n"
        f"Jami ovozlar: <b>{summary['total']}</b>\n\n"
        "Xizmatimiz sizga qanchalik yoqqanini baholang 💗"
    )
    bot.send_message(chat_id, text, reply_markup=markup)


def show_vip_bonus(chat_id: int, user_id: int) -> None:
    profile = get_user_profile(user_id)
    text = (
        "👑 <b>VIP & Bonus</b>\n\n"
        f"💗 Joriy bonus: <b>{format_currency(profile['bonus'])} UZS</b>\n"
        f"🌸 Status: <b>{html_escape(profile['vip_status'])}</b>\n"
        f"🪷 VIP uchun qoldi: <b>{max(0, VIP_VISITS - profile['visits'])}</b> tashrif\n\n"
        f"✨ Har yozilish uchun: +{format_currency(BONUS_PER_BOOKING)} UZS\n"
        f"👑 {VIP_VISITS} ta tashrifdan keyin: VIP status va {VIP_DISCOUNT_PERCENT}% chegirma\n"
        f"💗 Referal bonusi: do'stingiz bilan birga +{format_currency(REFERRAL_BONUS)} UZS\n"
        "📎 Referal havola uchun: /referral"
    )
    bot.send_message(chat_id, text, reply_markup=back_keyboard())


def show_location(chat_id: int) -> None:
    bot.send_location(chat_id, LOCATION["lat"], LOCATION["lon"])
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🗺 Yandex Maps", url=LOCATION["yandex"]),
        types.InlineKeyboardButton("📍 2GIS", url=LOCATION["two_gis"]),
    )
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_main"))
    bot.send_message(
        chat_id,
        "📍 <b>Go'zallik studiyamiz manzili</b>\n"
        f"{html_escape(LOCATION['address'])}\n\n"
        f"🪷 <b>Ish vaqti:</b> {html_escape(LOCATION['schedule'])}",
        reply_markup=markup,
    )


def send_booking_confirmation(chat_id: int, user_id: int) -> None:
    state = get_state(user_id)
    if not state:
        bot.send_message(chat_id, "Bron qilish bosqichlari yangidan boshlanadi.", reply_markup=back_keyboard())
        return
    bot.send_message(chat_id, build_confirmation_text(state), reply_markup=confirm_keyboard())


def send_phone_request(chat_id: int, user_id: int) -> None:
    set_state(user_id, step="awaiting_contact", source="bot")
    bot.send_message(
        chat_id,
        "5️⃣ <b>Telefon raqamingizni yuboring</b>\n\n"
        "«Raqamni yuborish» tugmasini bosing yoki raqamni qo'lda yozing.",
        reply_markup=request_contact_keyboard(),
    )


def notify_webapp_booking(user_id: int, result: dict[str, Any]) -> None:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_main"))
    markup.add(types.InlineKeyboardButton("🚀 Mini App", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    try:
        bot.send_message(user_id, build_success_text(result), reply_markup=markup)
    except Exception as exc:
        logger.warning("Could not notify user about WebApp booking: %s", exc)


def serialize_profile(user_id: int) -> dict[str, Any]:
    profile = get_user_profile(user_id)
    return {
        "userId": profile["user_id"],
        "name": profile["full_name"],
        "phone": profile["phone"],
        "bonus": profile["bonus"],
        "visits": profile["visits"],
        "vipStatus": profile["vip_status"],
        "refCode": profile["ref_code"],
        "remainingForFree": profile["remaining_for_free"],
        "upcoming": [
            {
                "id": booking["id"],
                "service": booking["service"],
                "master": booking["master"],
                "date": booking["date"],
                "dateLabel": display_date(booking["date"]),
                "time": booking["time"],
            }
            for booking in profile["upcoming"]
        ],
    }


def serialize_public_config() -> dict[str, Any]:
    return {
        "brand": BRAND_NAME,
        "subtitle": BRAND_SUBTITLE,
        "heroPhoto": PHOTO_URL,
        "bonusPerBooking": BONUS_PER_BOOKING,
        "vipVisits": VIP_VISITS,
        "vipDiscountPercent": VIP_DISCOUNT_PERCENT,
        "referralBonus": REFERRAL_BONUS,
        "workingHours": LOCATION["schedule"],
        "address": LOCATION["address"],
        "botLink": BOT_LINK,
        "webAppUrl": WEBAPP_URL,
        "services": SERVICES,
        "masters": MASTERS,
        "timeSlots": TIME_SLOTS,
        "today": get_today().isoformat(),
        "location": LOCATION,
        "bookingWindowDays": BOOKING_WINDOW_DAYS,
    }


def parse_telegram_init_data(init_data: str) -> dict[str, Any]:
    if not init_data:
        raise AuthError("Telegram init data yuborilmadi.")

    data = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = data.pop("hash", "")
    if not received_hash and not ALLOW_UNSAFE_WEBAPP_DEV:
        raise AuthError("Telegram init data hash topilmadi.")

    if received_hash:
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        secret_key = hmac.new(b"WebAppData", TOKEN.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            raise AuthError("Telegram init data imzosi noto'g'ri.")

    auth_date = int(data.get("auth_date", "0") or "0")
    if auth_date and (time.time() - auth_date) > 86400:
        raise AuthError("Telegram sessiyasi eskirib qolgan.")

    user_payload = data.get("user")
    if not user_payload:
        raise AuthError("Telegram foydalanuvchi ma'lumoti kelmadi.")

    try:
        data["user"] = json.loads(user_payload)
    except json.JSONDecodeError as exc:
        raise AuthError("Telegram foydalanuvchi ma'lumoti buzilgan.") from exc

    return data


def get_telegram_user_from_request(payload: dict[str, Any]) -> dict[str, Any]:
    verified = parse_telegram_init_data(payload.get("initData", ""))
    user = verified["user"]
    if "id" not in user:
        raise AuthError("Telegram foydalanuvchi ID topilmadi.")
    return user


async def json_body(request: web.Request) -> dict[str, Any]:
    try:
        return await request.json()
    except Exception as exc:
        raise ValidationError("JSON body noto'g'ri.") from exc


@web.middleware
async def cors_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@web.middleware
async def api_error_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    try:
        return await handler(request)
    except AuthError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=401)
    except SlotTakenError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=409)
    except ValidationError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Unhandled API error: %s", exc)
        return web.json_response({"ok": False, "error": "Serverda kutilmagan xatolik yuz berdi."}, status=500)


async def health_handler(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "beauty_studio"})


async def init_handler(request: web.Request) -> web.Response:
    payload = await json_body(request)
    user = get_telegram_user_from_request(payload)
    full_name = " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part)
    init_user(int(user["id"]), full_name=full_name)
    return web.json_response(
        {
            "ok": True,
            "config": serialize_public_config(),
            "profile": serialize_profile(int(user["id"])),
        }
    )


async def profile_handler(request: web.Request) -> web.Response:
    payload = await json_body(request)
    user = get_telegram_user_from_request(payload)
    return web.json_response({"ok": True, "profile": serialize_profile(int(user["id"]))})


async def slots_handler(request: web.Request) -> web.Response:
    master_id = request.query.get("master_id", "")
    date_str = request.query.get("date", "")
    master = get_master(master_id)
    validate_date(date_str)
    taken = get_taken_slots(master["name"], date_str)
    slots = [{"time": slot, "available": slot not in taken} for slot in TIME_SLOTS]
    return web.json_response({"ok": True, "slots": slots})


async def book_handler(request: web.Request) -> web.Response:
    payload = await json_body(request)
    user = get_telegram_user_from_request(payload)
    user_id = int(user["id"])
    full_name = " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part).strip()
    profile = get_user_profile(user_id)

    phone = payload.get("phone") or profile.get("phone") or ""
    name = payload.get("name") or profile.get("full_name") or full_name or "Mijoz"
    result = create_booking(
        user_id,
        service_id=payload.get("serviceId", ""),
        master_id=payload.get("masterId", ""),
        date_str=payload.get("date", ""),
        time_str=payload.get("time", ""),
        phone=phone,
        name=name,
        source="mini_app",
    )
    send_admin_notification(result)
    if result.get("referral_awarded") and result.get("referrer_id"):
        notify_referral_bonus(result["referrer_id"], user_id)
    notify_webapp_booking(user_id, result)
    return web.json_response(
        {
            "ok": True,
            "booking": {
                "id": result["booking_id"],
                "service": result["service_name"],
                "master": result["master_name"],
                "date": result["date"],
                "dateLabel": display_date(result["date"]),
                "time": result["time"],
                "bonus": result["bonus"],
                "remainingForFree": result["remaining_for_free"],
                "discountPercent": result["discount_percent"],
                "finalPrice": result["final_price"],
                "vipStatus": result["vip_status"],
            },
        }
    )


def create_web_app() -> web.Application:
    app = web.Application(middlewares=[api_error_middleware, cors_middleware])
    app.router.add_get("/", lambda _: web.HTTPFound("/mini_app/index.html"))
    app.router.add_get("/health", health_handler)
    app.router.add_post("/api/init", init_handler)
    app.router.add_post("/api/profile", profile_handler)
    app.router.add_get("/api/slots", slots_handler)
    app.router.add_post("/api/book", book_handler)
    app.router.add_static("/mini_app/", str(MINI_APP_DIR), show_index=True)
    return app


def start_web_server() -> None:
    app = create_web_app()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    loop.run_until_complete(site.start())
    logger.info("Mini App server started on http://%s:%s", WEBAPP_HOST, WEBAPP_PORT)
    loop.run_forever()


def send_due_notifications_once() -> None:
    reminder_ids: list[int] = []
    review_ids: list[int] = []
    reminder_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    now = get_now()

    with db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT id, user_id, service, master, date, time, reminder_sent, review_request_sent, status
                FROM bookings
                WHERE status = 'active'
                """
            ).fetchall()
        finally:
            conn.close()

    for row in rows:
        booking = dict(row)
        try:
            visit_dt = booking_datetime(booking["date"], booking["time"])
        except Exception:
            continue

        reminder_delta = visit_dt - now
        if not booking["reminder_sent"] and dt.timedelta(hours=23) <= reminder_delta <= dt.timedelta(hours=25):
            reminder_rows.append(booking)

        review_delta = now - visit_dt
        if not booking["review_request_sent"] and review_delta >= dt.timedelta(hours=2):
            review_rows.append(booking)

    for booking in reminder_rows:
        try:
            bot.send_message(
                booking["user_id"],
                f"🌸 Eslatma! Ertaga {booking['time']} da {booking['service']} xizmatingiz bor.\n"
                f"Ustangiz: {booking['master']} 💅",
            )
            reminder_ids.append(booking["id"])
        except Exception as exc:
            logger.warning("Reminder send failed for booking %s: %s", booking["id"], exc)

    for booking in review_rows:
        try:
            markup = types.InlineKeyboardMarkup(row_width=5)
            markup.row(*[
                types.InlineKeyboardButton("⭐" * star, callback_data=f"post_visit_{booking['id']}_{star}")
                for star in range(1, 6)
            ])
            bot.send_message(
                booking["user_id"],
                "✨ Qabulingiz yoqdimi? Baho bering! ⭐⭐⭐⭐⭐",
                reply_markup=markup,
            )
            review_ids.append(booking["id"])
        except Exception as exc:
            logger.warning("Post-visit review send failed for booking %s: %s", booking["id"], exc)

    if reminder_ids or review_ids:
        with db_lock:
            conn = get_conn()
            try:
                if reminder_ids:
                    conn.executemany(
                        "UPDATE bookings SET reminder_sent = 1 WHERE id = ?",
                        [(booking_id,) for booking_id in reminder_ids],
                    )
                if review_ids:
                    conn.executemany(
                        "UPDATE bookings SET review_request_sent = 1 WHERE id = ?",
                        [(booking_id,) for booking_id in review_ids],
                    )
                conn.commit()
            finally:
                conn.close()


def start_scheduler_loop() -> None:
    while True:
        try:
            send_due_notifications_once()
        except Exception as exc:
            logger.exception("Scheduler loop failed: %s", exc)
        time.sleep(60)


def configure_bot_ui() -> None:
    global BOT_LINK

    try:
        commands = [
            types.BotCommand("start", "Asosiy menyu"),
            types.BotCommand("admin", "Admin panel"),
            types.BotCommand("referral", "Referal havola"),
        ]
        bot.set_my_commands(commands)
    except Exception as exc:
        logger.warning("Could not set commands: %s", exc)

    try:
        bot_info = bot.get_me()
        if not BOT_LINK and getattr(bot_info, "username", None):
            BOT_LINK = f"https://t.me/{bot_info.username}"
    except Exception as exc:
        logger.warning("Could not fetch bot username: %s", exc)

    try:
        menu_button_class = getattr(types, "MenuButtonWebApp", None)
        if menu_button_class:
            bot.set_chat_menu_button(menu_button=menu_button_class("Mini App", types.WebAppInfo(WEBAPP_URL)))
    except Exception as exc:
        logger.warning("Could not configure menu button: %s", exc)


@bot.message_handler(commands=["start", "menu"])
def start_command(message: types.Message) -> None:
    try:
        full_name = " ".join(part for part in [message.from_user.first_name, message.from_user.last_name] if part)
        init_user(message.from_user.id, full_name=full_name)
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].split("_", 1)[1])
                if attach_referrer(message.from_user.id, referrer_id):
                    bot.send_message(
                        message.chat.id,
                        f"💗 Referal havola qabul qilindi!\n\nBirinchi yozilishdan keyin siz va do'stingizga +{format_currency(REFERRAL_BONUS)} UZS bonus qo'shiladi.",
                    )
            except ValueError:
                pass
        clear_state(message.from_user.id)
        send_main_menu(message.chat.id, message.from_user.id)
    except Exception as exc:
        logger.exception("Start handler failed: %s", exc)
        bot.send_message(message.chat.id, "Asosiy menyuni ochishda xatolik yuz berdi. /start ni qayta yuboring.")


@bot.message_handler(commands=["referral"])
def referral_command(message: types.Message) -> None:
    try:
        init_user(message.from_user.id)
        link = build_referral_link(message.from_user.id)
        profile = get_user_profile(message.from_user.id)
        text = (
            "💗 <b>Referal dasturi</b>\n\n"
            f"Sizning kodingiz: <code>{html_escape(profile['ref_code'])}</code>\n"
            f"Bonus: sizga ham, do'stingizga ham +{format_currency(REFERRAL_BONUS)} UZS\n\n"
            f"Havola:\n{html_escape(link) if link else 'Bot username aniqlanmagan.'}"
        )
        bot.send_message(message.chat.id, text)
    except Exception as exc:
        logger.exception("Referral handler failed: %s", exc)
        bot.send_message(message.chat.id, "Referal havolani yaratishda xatolik yuz berdi.")


@bot.message_handler(commands=["admin"])
def admin_panel(message: types.Message) -> None:
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Sizda admin huquqi yo'q.")
        return

    bookings = get_admin_bookings()
    if not bookings:
        bot.send_message(message.chat.id, "📭 Bugun va keyingi kunlar uchun faol yozilishlar yo'q.")
        return

    text_lines = ["🌸 <b>Kelgusi yozilishlar</b>\n"]
    for booking in bookings:
        text_lines.append(
            f"🧾 <b>#{booking['id']}</b>\n"
            f"🪷 {html_escape(display_date(booking['date']))}, {html_escape(booking['time'])}\n"
            f"👤 {html_escape(booking['name'])}\n"
            f"📱 {html_escape(booking['phone'])}\n"
            f"💗 {html_escape(booking['service'])}\n"
            f"✨ {html_escape(booking['master'])}\n"
            f"📲 {html_escape(booking['source'])}\n"
            f"/cancel_{booking['id']}"
        )
    bot.send_message(message.chat.id, "\n\n".join(text_lines))


@bot.message_handler(func=lambda message: bool(message.text and message.text.startswith("/cancel_")))
def cancel_from_admin(message: types.Message) -> None:
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Sizda admin huquqi yo'q.")
        return
    try:
        booking_id = int(message.text.split("_", 1)[1])
    except Exception:
        bot.send_message(message.chat.id, "❌ Booking ID noto'g'ri.")
        return

    if cancel_booking_as_admin(booking_id):
        bot.send_message(message.chat.id, f"🌸 #{booking_id} yozilish bekor qilindi.")
    else:
        bot.send_message(message.chat.id, "❌ Yozilish topilmadi yoki avval bekor qilingan.")


def process_contact_payload(message: types.Message, phone: str, name: str) -> None:
    user_id = message.from_user.id
    state = get_state(user_id)

    init_user(user_id, full_name=name, phone=phone)
    set_state(user_id, phone=phone, name=name)

    if state.get("source") == "bot" and state.get("step") == "awaiting_contact":
        set_state(user_id, step="awaiting_confirmation")
        bot.send_message(
            message.chat.id,
            "🌸 Ma'lumotlar qabul qilindi.",
            reply_markup=types.ReplyKeyboardRemove(),
        )
        send_booking_confirmation(message.chat.id, user_id)
        return

    bot.send_message(
        message.chat.id,
        "💗 Telefon raqamingiz saqlandi.",
        reply_markup=types.ReplyKeyboardRemove(),
    )


@bot.message_handler(content_types=["contact"])
def handle_contact(message: types.Message) -> None:
    try:
        contact = message.contact
        phone = normalize_phone(contact.phone_number if contact else "")
        name = contact.first_name if contact and contact.first_name else (message.from_user.first_name or "Mijoz")
        process_contact_payload(message, phone, name)
    except Exception as exc:
        logger.exception("Contact handler failed: %s", exc)
        bot.send_message(message.chat.id, "Telefon raqamini qabul qilishda xatolik yuz berdi.")


@bot.message_handler(content_types=["web_app_data"])
def handle_webapp_data(message: types.Message) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
        result = create_booking(
            message.from_user.id,
            service_id=payload.get("serviceId", ""),
            master_id=payload.get("masterId", ""),
            date_str=payload.get("date", ""),
            time_str=payload.get("time", ""),
            phone=payload.get("phone", ""),
            name=payload.get("name") or message.from_user.first_name or "Mijoz",
            source="web_app_data",
        )
        send_admin_notification(result)
        if result.get("referral_awarded") and result.get("referrer_id"):
            notify_referral_bonus(result["referrer_id"], message.from_user.id)
        bot.send_message(message.chat.id, build_success_text(result), reply_markup=back_keyboard())
    except Exception as exc:
        logger.exception("Web app data handler failed: %s", exc)
        bot.send_message(message.chat.id, "Mini App ma'lumotlarini saqlashda xatolik yuz berdi.")


@bot.message_handler(content_types=["text"])
def handle_text_message(message: types.Message) -> None:
    if not message.text:
        return
    if message.text == "🏠 Asosiy menyu":
        clear_state(message.from_user.id)
        send_main_menu(message.chat.id, message.from_user.id)
        return

    state = get_state(message.from_user.id)
    if state.get("source") == "bot" and state.get("step") == "awaiting_contact":
        if looks_like_phone(message.text):
            phone = normalize_phone(message.text)
            name = message.from_user.first_name or "Mijoz"
            process_contact_payload(message, phone, name)
        else:
            bot.send_message(
                message.chat.id,
                "Telefon raqamini to'liq formatda yuboring yoki «Raqamni yuborish» tugmasini bosing 💗",
            )
        return

    send_main_menu(message.chat.id, message.from_user.id)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: types.CallbackQuery) -> None:
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_id = call.from_user.id
    data = call.data

    try:
        if data == "ignore":
            safe_answer_callback(call.id)
            return

        if data == "slot_taken":
            safe_answer_callback(call.id, "Bu vaqt band. Boshqa vaqtni tanlang.", show_alert=True)
            return

        if data == "back_main":
            safe_delete(chat_id, message_id)
            clear_state(user_id)
            send_main_menu(chat_id, user_id)
            return

        if data == "services":
            safe_delete(chat_id, message_id)
            show_services(chat_id)
            return

        if data == "vip_bonus":
            safe_delete(chat_id, message_id)
            show_vip_bonus(chat_id, user_id)
            return

        if data.startswith("info_service_"):
            service = get_service(data.replace("info_service_", ""))
            safe_answer_callback(
                call.id,
                f"{service['name']} — {format_currency(service['price'])} UZS",
                show_alert=True,
            )
            return

        if data == "cabinet":
            safe_delete(chat_id, message_id)
            show_cabinet(chat_id, user_id)
            return

        if data.startswith("cancel_booking_"):
            booking_id = int(data.replace("cancel_booking_", ""))
            if cancel_booking_for_user(user_id, booking_id):
                safe_answer_callback(call.id, "Qabulingiz bekor qilindi.", show_alert=True)
            else:
                safe_answer_callback(call.id, "Qabul topilmadi yoki allaqachon bekor qilingan.", show_alert=True)
            safe_delete(chat_id, message_id)
            show_cabinet(chat_id, user_id)
            return

        if data == "reviews":
            safe_delete(chat_id, message_id)
            show_reviews(chat_id)
            return

        if data.startswith("post_visit_"):
            payload = data.replace("post_visit_", "", 1)
            booking_id, stars = payload.rsplit("_", 1)
            store_review(user_id, int(stars))
            safe_answer_callback(call.id, f"{stars} ⭐ uchun rahmat!")
            bot.edit_message_text(
                "💗 <b>Rahmat!</b>\n\nBahoyingiz qabul qilindi va bu biz uchun juda qadrli.",
                chat_id,
                message_id,
                reply_markup=back_keyboard(),
            )
            return

        if data.startswith("review_"):
            stars = int(data.split("_", 1)[1])
            store_review(user_id, stars)
            safe_answer_callback(call.id, f"{stars} ⭐ uchun rahmat!")
            bot.edit_message_text(
                "💗 <b>Sharhingiz qabul qilindi!</b>\n\n"
                "Fikrlaringiz xizmatimizni yanada go'zal qilishga yordam beradi.",
                chat_id,
                message_id,
                reply_markup=back_keyboard(),
            )
            return

        if data == "location":
            safe_delete(chat_id, message_id)
            show_location(chat_id)
            return

        if data == "booking_start":
            clear_state(user_id)
            set_state(user_id, source="bot", step="choosing_service")
            safe_delete(chat_id, message_id)
            bot.send_message(chat_id, "1️⃣ <b>🌸 Xizmatni tanlang</b>", reply_markup=services_keyboard(is_booking=True))
            return

        if data.startswith("book_service_"):
            service = get_service(data.replace("book_service_", ""))
            set_state(
                user_id,
                step="choosing_master",
                service_id=service["id"],
                service_name=service["name"],
                service_price=service["price"],
            )
            bot.edit_message_text(
                "2️⃣ <b>✨ Ustani tanlang</b>",
                chat_id,
                message_id,
                reply_markup=masters_keyboard(),
            )
            return

        if data == "back_masters":
            bot.edit_message_text(
                "2️⃣ <b>✨ Ustani tanlang</b>",
                chat_id,
                message_id,
                reply_markup=masters_keyboard(),
            )
            return

        if data.startswith("book_master_"):
            master = get_master(data.replace("book_master_", ""))
            set_state(
                user_id,
                step="choosing_date",
                master_id=master["id"],
                master_name=master["name"],
            )
            bot.edit_message_text(
                "3️⃣ <b>🪷 Kunni tanlang</b>",
                chat_id,
                message_id,
                reply_markup=create_calendar(),
            )
            return

        if data.startswith("cal_"):
            _, year, month = data.split("_")
            bot.edit_message_reply_markup(
                chat_id,
                message_id,
                reply_markup=create_calendar(int(year), int(month)),
            )
            return

        if data == "back_calendar":
            state = get_state(user_id)
            selected_date = state.get("date", "")
            if selected_date:
                selected = dt.date.fromisoformat(selected_date)
                markup = create_calendar(selected.year, selected.month)
            else:
                markup = create_calendar()
            bot.edit_message_text(
                "3️⃣ <b>🪷 Kunni tanlang</b>",
                chat_id,
                message_id,
                reply_markup=markup,
            )
            return

        if data.startswith("book_date_"):
            date_str = data.replace("book_date_", "")
            validate_booking_datetime(date_str, TIME_SLOTS[0])
            state = get_state(user_id)
            if not state.get("master_name"):
                raise ValidationError("Avval master tanlang.")
            set_state(user_id, step="choosing_time", date=date_str)
            bot.edit_message_text(
                f"🪷 <b>{html_escape(display_date(date_str))}</b>\n\n"
                "4️⃣ <b>💗 Vaqtni tanlang</b>\n"
                "🟢 Bo'sh   🔴 Band",
                chat_id,
                message_id,
                reply_markup=times_keyboard(state["master_name"], date_str),
            )
            return

        if data.startswith("book_time_"):
            time_str = data.replace("book_time_", "")
            state = get_state(user_id)
            if not state.get("master_name") or not state.get("date"):
                raise ValidationError("Bron ma'lumotlari to'liq emas. Qaytadan boshlang.")
            taken = get_taken_slots(state["master_name"], state["date"])
            if time_str in taken:
                safe_answer_callback(call.id, "Bu vaqt allaqachon band.", show_alert=True)
                bot.edit_message_reply_markup(
                    chat_id,
                    message_id,
                    reply_markup=times_keyboard(state["master_name"], state["date"]),
                )
                return

            set_state(user_id, step="awaiting_contact", time=time_str)
            safe_delete(chat_id, message_id)
            send_phone_request(chat_id, user_id)
            return

        if data == "book_confirm":
            state = get_state(user_id)
            required = ["service_id", "master_id", "date", "time", "phone"]
            if not all(state.get(field) for field in required):
                raise ValidationError("Bron ma'lumotlari yetarli emas. Qaytadan boshlang.")

            result = create_booking(
                user_id,
                service_id=state["service_id"],
                master_id=state["master_id"],
                date_str=state["date"],
                time_str=state["time"],
                phone=state["phone"],
                name=state.get("name") or call.from_user.first_name or "Mijoz",
                source="bot",
            )
            clear_state(user_id)
            send_admin_notification(result)
            if result.get("referral_awarded") and result.get("referrer_id"):
                notify_referral_bonus(result["referrer_id"], user_id)
            safe_delete(chat_id, message_id)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_main"))
            markup.add(types.InlineKeyboardButton("🚀 Mini App", web_app=types.WebAppInfo(url=WEBAPP_URL)))
            bot.send_message(chat_id, build_success_text(result), reply_markup=markup)
            return

        safe_answer_callback(call.id, "Bu tugma hozircha faol emas.", show_alert=True)
    except SlotTakenError as exc:
        logger.warning("Slot taken in callback flow: %s", exc)
        safe_answer_callback(call.id, str(exc), show_alert=True)
    except ValidationError as exc:
        safe_answer_callback(call.id, str(exc), show_alert=True)
    except Exception as exc:
        logger.exception("Callback handler failed: %s", exc)
        safe_answer_callback(call.id, "Xatolik yuz berdi. Qayta urinib ko'ring.", show_alert=True)


def start_services() -> None:
    init_db()
    configure_bot_ui()
    web_thread = threading.Thread(target=start_web_server, name="mini-app-server", daemon=True)
    web_thread.start()
    scheduler_thread = threading.Thread(target=start_scheduler_loop, name="scheduler-loop", daemon=True)
    scheduler_thread.start()


def remove_webhook_if_needed() -> None:
    try:
        bot.remove_webhook()
    except Exception:
        try:
            bot.delete_webhook()
        except Exception as exc:
            logger.warning("Could not remove webhook: %s", exc)


def run_polling_forever() -> None:
    backoff = 2
    while True:
        try:
            remove_webhook_if_needed()
            logger.info("Beauty Studio bot ishga tushdi...")
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True,
            )
        except KeyboardInterrupt:
            logger.info("Bot manually stopped.")
            raise
        except Exception as exc:
            logger.exception("Polling crashed: %s", exc)
            time.sleep(backoff)
            backoff = min(backoff * 2, 20)


if __name__ == "__main__":
    start_services()
    run_polling_forever()
