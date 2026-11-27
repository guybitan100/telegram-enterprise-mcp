import asyncio
import hashlib
import json
import logging
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from .auth import is_admin_private
from .config import (
    BOT_TOKEN,
    DATA_DIR,
    EXPECTED_BOT_USERNAME,
    LOG_LEVEL,
    MAX_UPLOAD_BYTES,
    PREVIEW_SECONDS,
    PRICE_STARS,
    SUPPORT_HANDLE,
)


logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger("nova-isr")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
BOT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = BOT_ROOT / "catalog.json"
LOCAL_TRACK_DIR = BOT_ROOT / "mp3" / "nova_isr"
db = sqlite3.connect(DATA_DIR / "store.db", timeout=30)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA busy_timeout=30000")
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS tracks(
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        cover TEXT,
        full TEXT NOT NULL,
        preview TEXT NOT NULL,
        hash TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS orders(
        id TEXT PRIMARY KEY,
        uid INTEGER NOT NULL,
        track INTEGER NOT NULL,
        amount INTEGER NOT NULL DEFAULT 50,
        paid INTEGER NOT NULL DEFAULT 0,
        charge TEXT UNIQUE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_pending
        ON orders(uid, track) WHERE paid=0;
    """
)
try:
    db.execute("ALTER TABLE orders ADD COLUMN amount INTEGER NOT NULL DEFAULT 50")
except sqlite3.OperationalError as exc:
    if "duplicate column name" not in str(exc).lower():
        raise
for column, definition in (("description", "TEXT NOT NULL DEFAULT ''"), ("cover", "TEXT")):
    try:
        db.execute(f"ALTER TABLE tracks ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as exc:
        if f"duplicate column name: {column}" not in str(exc).lower():
            raise
db.commit()

# Handlers share one SQLite connection. Serialize mutations and payment checks.
db_lock = asyncio.Lock()


def keyboard(rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in rows
        ]
    )


def id_from_callback(data: str, prefix: str) -> int | None:
    try:
        if not data.startswith(prefix):
            return None
        return int(data[len(prefix) :])
    except ValueError:
        return None


def get_track(track_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()


def track_caption(row: sqlite3.Row) -> str:
    description = (row["description"] or "").strip()
    return f"{row['title']}\n\n{description}"[:1024] if description else row["title"]


def build_preview(source: Path, preview: Path) -> None:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    duration = float(probe.stdout.strip())
    if duration < PREVIEW_SECONDS:
        raise ValueError(f"track is shorter than {PREVIEW_SECONDS} seconds")
    start = max(0, (duration - PREVIEW_SECONDS) / 2)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-t",
            str(PREVIEW_SECONDS),
            "-af",
            f"afade=t=in:d=0.5,afade=t=out:st={max(0, PREVIEW_SECONDS - 1)}:d=1",
            "-map_metadata",
            "-1",
            "-vn",
            str(preview),
        ],
        check=True,
        timeout=120,
    )


def sync_local_catalog() -> None:
    """Publish local MP3s into the catalog using checked-in metadata."""
    if not CATALOG_FILE.is_file():
        return
    try:
        catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Could not read local catalog")
        return

    for item in catalog:
        source = LOCAL_TRACK_DIR / item["file"]
        if not source.is_file():
            log.warning("Catalog track is missing: %s", source)
            continue
        try:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            full = DATA_DIR / f"{digest}.mp3"
            preview = DATA_DIR / f"{digest}-preview.mp3"
            if not full.is_file():
                shutil.copyfile(source, full)
            if not preview.is_file():
                build_preview(source, preview)
            cover_path = None
            cover_url = item.get("cover_url")
            if cover_url:
                cover = DATA_DIR / "covers" / f"{digest}.jpg"
                cover.parent.mkdir(parents=True, exist_ok=True)
                if not cover.is_file():
                    try:
                        with urllib.request.urlopen(cover_url, timeout=30) as response:
                            cover.write_bytes(response.read())
                    except OSError:
                        log.warning("Could not download cover for %s", source)
                if cover.is_file():
                    cover_path = str(cover)
            db.execute(
                """
                INSERT INTO tracks(title, description, cover, full, preview, hash)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(hash) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    cover=excluded.cover,
                    full=excluded.full,
                    preview=excluded.preview
                """,
                (
                    item["title"][:120],
                    item.get("description", "")[:900],
                    cover_path,
                    str(full),
                    str(preview),
                    digest,
                ),
            )
        except (OSError, ValueError, subprocess.SubprocessError, sqlite3.Error):
            log.exception("Could not index local track: %s", source)
    db.commit()


def is_owned(user_id: int, track_id: int) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM orders WHERE uid=? AND track=? AND paid=1",
            (user_id, track_id),
        ).fetchone()
    )


async def pending_order(user_id: int, track_id: int) -> sqlite3.Row:
    """Return one pending order, creating it safely under concurrent callbacks."""
    async with db_lock:
        row = db.execute(
            "SELECT * FROM orders WHERE uid=? AND track=? AND paid=0",
            (user_id, track_id),
        ).fetchone()
        if row:
            return row
        order_id = secrets.token_urlsafe(18)
        try:
            db.execute(
                "INSERT INTO orders(id, uid, track, amount) VALUES(?,?,?,?)",
                (order_id, user_id, track_id, PRICE_STARS),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            row = db.execute(
                "SELECT * FROM orders WHERE uid=? AND track=? AND paid=0",
                (user_id, track_id),
            ).fetchone()
            if row:
                return row
            raise
        return db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()


async def record_payment(payment, user_id: int) -> tuple[str, sqlite3.Row | None]:
    """Atomically accept a payment, reject mismatches, and make replays safe."""
    async with db_lock:
        row = db.execute(
            "SELECT * FROM orders WHERE id=?", (payment.invoice_payload,)
        ).fetchone()
        valid = bool(
            row
            and row["uid"] == user_id
            and payment.currency == "XTR"
            and payment.total_amount == row["amount"]
            and get_track(row["track"])
        )
        if not valid:
            return "invalid", row
        if row["paid"]:
            return (
                "replay" if row["charge"] == payment.telegram_payment_charge_id else "duplicate",
                row,
            )
        db.execute(
            "UPDATE orders SET paid=1, charge=? WHERE id=? AND paid=0",
            (payment.telegram_payment_charge_id, row["id"]),
        )
        db.commit()
        return "accepted", db.execute(
            "SELECT * FROM orders WHERE id=?", (row["id"],)
        ).fetchone()


async def deliver(chat_id: int, user_id: int, track_id: int) -> None:
    row = get_track(track_id)
    if not row or not is_owned(user_id, track_id):
        return
    full = Path(row["full"])
    if not full.is_file():
        log.error("Missing media for track_id=%s", track_id)
        await bot.send_message(chat_id, "This download is temporarily unavailable. Contact support.")
        return
    await bot.send_document(chat_id, FSInputFile(full), caption=track_caption(row))


@dp.message(Command("start", "music"))
async def start(message: Message) -> None:
    rows = db.execute("SELECT * FROM tracks ORDER BY id DESC").fetchall()
    buttons = [(row["title"][:45], f"t:{row['id']}") for row in rows]
    buttons.append(("My purchases", "purchases"))
    await message.answer(
        f"NOVA ISR ∞ Music Store\nFree {PREVIEW_SECONDS}-second previews • Full MP3: {PRICE_STARS} ⭐",
        reply_markup=keyboard(buttons),
    )


@dp.callback_query(F.data == "purchases")
async def purchases(query: CallbackQuery) -> None:
    await query.answer()
    rows = db.execute(
        "SELECT DISTINCT t.* FROM tracks t JOIN orders o ON t.id=o.track "
        "WHERE o.uid=? AND o.paid=1 ORDER BY t.id DESC",
        (query.from_user.id,),
    ).fetchall()
    markup = keyboard([(row["title"][:45], f"d:{row['id']}") for row in rows])
    await query.message.answer("Your purchases", reply_markup=markup if rows else None)


@dp.callback_query(F.data.startswith("t:"))
async def show(query: CallbackQuery) -> None:
    await query.answer()
    track_id = id_from_callback(query.data, "t:")
    row = get_track(track_id) if track_id is not None else None
    if not row or not Path(row["preview"]).is_file():
        await query.message.answer("Track unavailable.")
        return
    owned = is_owned(query.from_user.id, row["id"])
    await query.message.answer_audio(
        FSInputFile(row["preview"]),
        title=f"{row['title']} (Preview)",
        performer="NOVA ISR",
        caption=track_caption(row),
        thumbnail=FSInputFile(row["cover"]) if row["cover"] else None,
        reply_markup=keyboard(
            [
                (
                    "Download full MP3" if owned else f"Buy full MP3 • {PRICE_STARS} ⭐",
                    f"{'d' if owned else 'b'}:{row['id']}",
                )
            ]
        ),
    )


@dp.callback_query(F.data.startswith("d:"))
async def download(query: CallbackQuery) -> None:
    await query.answer()
    track_id = id_from_callback(query.data, "d:")
    if track_id is not None:
        await deliver(query.from_user.id, query.from_user.id, track_id)


@dp.callback_query(F.data.startswith("b:"))
async def buy(query: CallbackQuery) -> None:
    await query.answer()
    user_id = query.from_user.id
    track_id = id_from_callback(query.data, "b:")
    row = get_track(track_id) if track_id is not None else None
    if not row:
        return
    if is_owned(user_id, track_id):
        await deliver(user_id, user_id, track_id)
        return
    order = await pending_order(user_id, track_id)
    await bot.send_invoice(
        user_id,
        title=row["title"][:32],
        description=(row["description"] or "Original MP3 download")[:255],
        payload=order["id"],
        currency="XTR",
        prices=[LabeledPrice(label="Full MP3", amount=order["amount"])],
        provider_token="",
    )


@dp.pre_checkout_query()
async def checkout(query: PreCheckoutQuery) -> None:
    row = db.execute(
        "SELECT * FROM orders WHERE id=?", (query.invoice_payload,)
    ).fetchone()
    valid = bool(
        row
        and row["uid"] == query.from_user.id
        and not row["paid"]
        and not is_owned(row["uid"], row["track"])
        and query.currency == "XTR"
        and query.total_amount == row["amount"]
        and get_track(row["track"])
    )
    await query.answer(
        ok=valid,
        error_message=None if valid else "Order unavailable or already purchased.",
    )


@dp.message(F.successful_payment)
async def payment(message: Message) -> None:
    payment = message.successful_payment
    status, row = await record_payment(payment, message.from_user.id)
    if status == "duplicate":
        await bot.refund_star_payment(
            message.from_user.id, payment.telegram_payment_charge_id
        )
        await message.answer("Duplicate payment detected and refunded. Contact support if needed.")
        return
    if status == "invalid" or not row:
        await message.answer(f"Payment issue. Contact @{SUPPORT_HANDLE}.")
        return
    await deliver(message.chat.id, message.from_user.id, row["track"])


@dp.message(Command("paysupport"))
async def support(message: Message) -> None:
    await message.answer(f"Payment support: @{SUPPORT_HANDLE}")


@dp.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    if is_admin_private(message):
        await message.answer(
            "Send an MP3 as audio with its title in the caption. It will be published automatically. /stats"
        )


@dp.message(Command("stats"))
async def stats(message: Message) -> None:
    if is_admin_private(message):
        sales = db.execute("SELECT count(*) FROM orders WHERE paid=1").fetchone()[0]
        await message.answer(f"Sales: {sales} | Gross: {sales * PRICE_STARS} Stars")


@dp.message(F.audio)
async def upload(message: Message) -> None:
    if not is_admin_private(message):
        return
    audio = message.audio
    if (audio.file_size or 0) > MAX_UPLOAD_BYTES:
        await message.answer(
            f"MP3 must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB for this deployment."
        )
        return

    with tempfile.TemporaryDirectory(prefix="nova-upload-") as tmp:
        source = Path(tmp) / "input.mp3"
        preview_tmp = Path(tmp) / "preview.mp3"
        await bot.download(audio, destination=source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if db.execute("SELECT 1 FROM tracks WHERE hash=?", (digest,)).fetchone():
            await message.answer("Already published")
            return

        full = DATA_DIR / f"{digest}.mp3"
        preview = DATA_DIR / f"{digest}-preview.mp3"
        try:
            build_preview(source, preview_tmp)
            shutil.copyfile(source, full)
            shutil.copyfile(preview_tmp, preview)
            db.execute(
                """
                INSERT INTO tracks(title, description, cover, full, preview, hash)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    (message.caption or audio.title or "Untitled")[:120],
                    "",
                    None,
                    str(full),
                    str(preview),
                    digest,
                ),
            )
            db.commit()
            await message.answer("Published successfully")
        except (OSError, ValueError, subprocess.SubprocessError, sqlite3.Error):
            db.rollback()
            full.unlink(missing_ok=True)
            preview.unlink(missing_ok=True)
            log.exception("Upload processing failed")
            await message.answer("Upload processing failed. Check server logs.")


async def main() -> None:
    sync_local_catalog()
    me = await bot.get_me()
    if EXPECTED_BOT_USERNAME and (me.username or "").lower() != EXPECTED_BOT_USERNAME:
        raise RuntimeError(f"BOT_TOKEN belongs to @{me.username}, not @{EXPECTED_BOT_USERNAME}")
    log.info("Starting @%s", me.username)
    try:
        await dp.start_polling(bot)
    finally:
        db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
