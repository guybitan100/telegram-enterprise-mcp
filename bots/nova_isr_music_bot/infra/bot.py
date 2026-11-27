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
    InputPaidMediaVideo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PaidMediaPurchased,
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
from .presentation import display_title, id_from_callback


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
        campaign TEXT NOT NULL DEFAULT '',
        cover TEXT,
        full TEXT NOT NULL,
        preview TEXT NOT NULL,
        preview_video TEXT,
        paid_video TEXT,
        hash TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS orders(
        id TEXT PRIMARY KEY,
        uid INTEGER NOT NULL,
        track INTEGER NOT NULL,
        amount INTEGER NOT NULL DEFAULT 50,
        paid INTEGER NOT NULL DEFAULT 0,
        charge TEXT UNIQUE,
        invoice_message_id INTEGER
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_pending
        ON orders(uid, track) WHERE paid=0;
    CREATE TABLE IF NOT EXISTS reactions(
        uid INTEGER NOT NULL,
        track INTEGER NOT NULL,
        reaction TEXT NOT NULL,
        PRIMARY KEY(uid, track, reaction)
    );
    """
)
try:
    db.execute("ALTER TABLE orders ADD COLUMN amount INTEGER NOT NULL DEFAULT 50")
except sqlite3.OperationalError as exc:
    if "duplicate column name" not in str(exc).lower():
        raise
try:
    db.execute("ALTER TABLE orders ADD COLUMN invoice_message_id INTEGER")
except sqlite3.OperationalError as exc:
    if "duplicate column name" not in str(exc).lower():
        raise
for column, definition in (
    ("description", "TEXT NOT NULL DEFAULT ''"),
    ("campaign", "TEXT NOT NULL DEFAULT ''"),
    ("cover", "TEXT"),
    ("preview_video", "TEXT"),
    ("paid_video", "TEXT"),
):
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


def get_track(track_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()


def track_caption(row: sqlite3.Row) -> str:
    description = (row["description"] or "").strip()
    title = display_title(row["title"])
    return f"{title}\n\n{description}"[:1024] if description else title


def promotional_caption(row: sqlite3.Row) -> str:
    """Return a compact three-line campaign caption for a preview."""
    campaign = [line.strip() for line in (row["campaign"] or "").splitlines() if line.strip()]
    if len(campaign) == 3:
        return "\n".join(campaign)
    title = display_title(row["title"])
    description = " ".join((row["description"] or "").split())
    description = description[:150].rstrip(" .,;:-") or "Feel the sound."
    return (
        f"🎵 {title}\n"
        f"🔥 {description}\n"
        f"▶️ {PREVIEW_SECONDS}-second preview • Listen now"
    )


REACTIONS = (("❤️", "heart"), ("🥰", "love"), ("😍", "wow"), ("🔥", "fire"))


def reaction_key(data: str) -> tuple[int, str] | None:
    parts = data.split(":")
    valid = {key for _, key in REACTIONS}
    if len(parts) != 3 or parts[0] != "react" or not parts[1].isdigit():
        return None
    return (int(parts[1]), parts[2]) if parts[2] in valid else None


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


def build_preview_video(audio: Path, cover: Path, video: Path) -> None:
    """Create a Telegram video-player preview using the catalog cover art."""
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(cover),
            "-i",
            str(audio),
            "-t",
            str(PREVIEW_SECONDS),
            "-vf",
            "scale=720:720:force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(video),
        ],
        check=True,
        timeout=180,
    )


def build_paid_video(audio: Path, cover: Path, video: Path) -> None:
    """Create the full video Telegram reveals after a paid-media purchase."""
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(cover),
            "-i",
            str(audio),
            "-vf",
            "scale=720:720:force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(video),
        ],
        check=True,
        timeout=900,
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
            preview_video = DATA_DIR / f"{digest}-preview.mp4"
            paid_video = DATA_DIR / f"{digest}-paid.mp4"
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
            if cover_path and not preview_video.is_file():
                build_preview_video(preview, Path(cover_path), preview_video)
            if cover_path and not paid_video.is_file():
                build_paid_video(full, Path(cover_path), paid_video)
            db.execute(
                """
                INSERT INTO tracks(title, description, campaign, cover, full, preview, preview_video, paid_video, hash)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(hash) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    campaign=excluded.campaign,
                    cover=excluded.cover,
                    full=excluded.full,
                    preview=excluded.preview,
                    preview_video=excluded.preview_video,
                    paid_video=excluded.paid_video
                """,
                (
                    item["title"][:120],
                    item.get("description", "")[:900],
                    "\n".join(item.get("campaign", []))[:900],
                    cover_path,
                    str(full),
                    str(preview),
                    str(preview_video) if preview_video.is_file() else None,
                    str(paid_video) if paid_video.is_file() else None,
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
    if not row or not Path(row["full"]).is_file():
        await bot.send_message(chat_id, "The full track is temporarily unavailable.")
        return
    await bot.send_audio(
        chat_id,
        FSInputFile(row["full"]),
        title=display_title(row["title"]),
        performer="NOVA ISR",
        caption="Purchased download",
        protect_content=False,
    )


def preview_keyboard(track_id: int, user_id: int) -> InlineKeyboardMarkup:
    counts = {
        key: count
        for key, count in db.execute(
            "SELECT reaction, count(*) FROM reactions WHERE track=? GROUP BY reaction",
            (track_id,),
        ).fetchall()
    }
    selected = {
        reaction
        for (reaction,) in db.execute(
            "SELECT reaction FROM reactions WHERE track=? AND uid=?",
            (track_id, user_id),
        ).fetchall()
    }
    reaction_row = [
        InlineKeyboardButton(
            text=f"{emoji}{' ✓' if key in selected else ''} {counts.get(key, 0)}",
            callback_data=f"react:{track_id}:{key}",
        )
        for emoji, key in REACTIONS
    ]
    return InlineKeyboardMarkup(inline_keyboard=[reaction_row])


def preview_media_keyboard(track_id: int, user_id: int) -> InlineKeyboardMarkup:
    reactions = preview_keyboard(track_id, user_id).inline_keyboard[0]
    owned = is_owned(user_id, track_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬇️ Download" if owned else f"⬇️ Buy full song • {PRICE_STARS}⭐",
                    callback_data=f"d:{track_id}" if owned else f"b:{track_id}",
                )
            ],
            reactions,
        ]
    )


async def send_preview_video(
    message: Message, row: sqlite3.Row, user_id: int
) -> None:
    cover = Path(row["cover"]) if row["cover"] else None
    video = Path(row["preview_video"]) if row["preview_video"] else None
    paid_video = Path(row["paid_video"]) if row["paid_video"] else None
    caption = promotional_caption(row)
    markup = preview_media_keyboard(row["id"], user_id)
    if video and video.is_file():
        await message.answer_video(
            FSInputFile(video),
            duration=PREVIEW_SECONDS,
            width=720,
            height=720,
            caption=caption,
            thumbnail=FSInputFile(cover) if cover and cover.is_file() else None,
            supports_streaming=True,
            protect_content=True,
            reply_markup=markup,
        )
        return
    if paid_video and paid_video.is_file():
        await message.answer_paid_media(
            star_count=PRICE_STARS,
            media=[
                InputPaidMediaVideo(
                    media=FSInputFile(paid_video),
                    thumbnail=FSInputFile(cover) if cover and cover.is_file() else None,
                    cover=FSInputFile(cover) if cover and cover.is_file() else None,
                    width=720,
                    height=720,
                    supports_streaming=True,
                )
            ],
            payload=f"paid:{row['id']}",
            caption=caption,
            protect_content=True,
            reply_markup=preview_keyboard(row["id"], user_id),
        )
        return
    await message.answer_audio(
        FSInputFile(row["preview"]),
        title=f"{display_title(row['title'])} (30s Preview)",
        performer="NOVA ISR",
        caption=caption,
        thumbnail=FSInputFile(cover) if cover and cover.is_file() else None,
        protect_content=True,
        reply_markup=markup,
    )


@dp.purchased_paid_media()
async def purchased_paid_media(update: PaidMediaPurchased) -> None:
    """Record paid-media purchases so the normal download path remains available."""
    track_id = id_from_callback(update.paid_media_payload, "paid:")
    if track_id is None or not get_track(track_id):
        log.warning("Ignoring paid-media purchase with unknown payload: %s", update.paid_media_payload)
        return
    user_id = update.from_user.id
    order_id = f"paid:{user_id}:{track_id}:{update.paid_media_payload}"
    async with db_lock:
        db.execute(
            """
            INSERT OR IGNORE INTO orders(id, uid, track, amount, paid, charge)
            VALUES(?,?,?,?,1,?)
            """,
            (order_id, user_id, track_id, PRICE_STARS, order_id),
        )
        db.commit()


@dp.message(Command("start", "music"))
async def start(message: Message) -> None:
    rows = db.execute("SELECT * FROM tracks ORDER BY id DESC").fetchall()
    if not rows:
        await message.answer("No previews are available right now.")
        return
    await message.answer(
        "NOVA ISR ∞ Music Store\nAll protected 30-second previews:",
    )
    for row in rows:
        if Path(row["preview"]).is_file():
            await send_preview_video(message, row, message.from_user.id)


@dp.callback_query(F.data == "purchases")
async def purchases(query: CallbackQuery) -> None:
    await query.answer()
    rows = db.execute(
        "SELECT DISTINCT t.* FROM tracks t JOIN orders o ON t.id=o.track "
        "WHERE o.uid=? AND o.paid=1 ORDER BY t.id DESC",
        (query.from_user.id,),
    ).fetchall()
    markup = keyboard(
        [(display_title(row["title"])[:45], f"d:{row['id']}") for row in rows]
    )
    await query.message.answer("Your purchases", reply_markup=markup if rows else None)


@dp.callback_query(F.data.startswith("t:"))
async def show(query: CallbackQuery) -> None:
    await query.answer()
    track_id = id_from_callback(query.data, "t:")
    row = get_track(track_id) if track_id is not None else None
    if not row or not Path(row["preview"]).is_file():
        await query.message.answer("Track unavailable.")
        return
    await send_preview_video(query.message, row, query.from_user.id)


@dp.callback_query(F.data.startswith("react:"))
async def react(query: CallbackQuery) -> None:
    parsed = reaction_key(query.data)
    if not parsed:
        await query.answer("Reaction unavailable.", show_alert=True)
        return
    track_id, reaction = parsed
    if not get_track(track_id):
        await query.answer("Track unavailable.", show_alert=True)
        return
    async with db_lock:
        existing = db.execute(
            "SELECT 1 FROM reactions WHERE uid=? AND track=? AND reaction=?",
            (query.from_user.id, track_id, reaction),
        ).fetchone()
        if existing:
            db.execute(
                "DELETE FROM reactions WHERE uid=? AND track=? AND reaction=?",
                (query.from_user.id, track_id, reaction),
            )
        else:
            db.execute(
                "INSERT INTO reactions(uid, track, reaction) VALUES(?,?,?)",
                (query.from_user.id, track_id, reaction),
            )
        db.commit()
    await query.answer("Reaction updated")
    row = get_track(track_id)
    if row:
        await query.message.edit_reply_markup(
            reply_markup=preview_keyboard(track_id, query.from_user.id)
        )


@dp.callback_query(F.data.startswith("d:"))
async def download(query: CallbackQuery) -> None:
    if getattr(query.message.chat, "type", "private") != "private":
        await query.answer("Downloads are available in private chat only.", show_alert=True)
        return
    track_id = id_from_callback(query.data, "d:")
    row = get_track(track_id) if track_id is not None else None
    if not row or not is_owned(query.from_user.id, track_id):
        await query.answer("Purchase required before downloading.", show_alert=True)
        return
    await query.answer("Sending your purchased track…")
    await deliver(query.message.chat.id, query.from_user.id, track_id)


@dp.callback_query(F.data.startswith("b:"))
async def buy(query: CallbackQuery) -> None:
    if getattr(query.message.chat, "type", "private") != "private":
        await query.answer("Purchases are available in private chat only.", show_alert=True)
        return
    track_id = id_from_callback(query.data, "b:")
    row = get_track(track_id) if track_id is not None else None
    if not row or not Path(row["full"]).is_file():
        await query.answer("Track unavailable.", show_alert=True)
        return
    if is_owned(query.from_user.id, track_id):
        await query.answer("Already purchased")
        await deliver(query.message.chat.id, query.from_user.id, track_id)
        return
    order = await pending_order(query.from_user.id, track_id)
    if order["invoice_message_id"]:
        await query.answer("Payment invoice already sent above.")
        return
    await query.answer()
    invoice = await query.message.answer_invoice(
        title=f"{display_title(row['title'])} — Full Track",
        description="Download the full MP3 file.",
        payload=order["id"],
        currency="XTR",
        prices=[LabeledPrice(label=display_title(row["title"]), amount=order["amount"])],
        provider_token="",
    )
    invoice_message_id = getattr(invoice, "message_id", None)
    if invoice_message_id is not None:
        async with db_lock:
            db.execute(
                "UPDATE orders SET invoice_message_id=? WHERE id=? AND paid=0",
                (invoice_message_id, order["id"]),
            )
            db.commit()


@dp.pre_checkout_query()
async def checkout(query: PreCheckoutQuery) -> None:
    row = db.execute(
        "SELECT * FROM orders WHERE id=? AND uid=? AND paid=0",
        (query.invoice_payload, query.from_user.id),
    ).fetchone()
    track = get_track(row["track"]) if row else None
    valid = bool(
        row
        and query.currency == "XTR"
        and query.total_amount == row["amount"]
        and track
        and Path(track["full"]).is_file()
    )
    await query.answer(
        ok=valid,
        error_message=None if valid else "This invoice is invalid or the track is unavailable.",
    )


@dp.message(F.successful_payment)
async def payment(message: Message) -> None:
    payment = message.successful_payment
    status, row = await record_payment(payment, message.from_user.id)
    if status == "accepted" and row:
        try:
            await deliver(message.chat.id, message.from_user.id, row["track"])
            return
        except Exception:
            log.exception("Could not deliver paid track")
            try:
                await bot.refund_star_payment(
                    message.from_user.id, payment.telegram_payment_charge_id
                )
            except Exception:
                log.exception("Could not refund an undeliverable paid track")
            await message.answer(f"Delivery failed. Contact @{SUPPORT_HANDLE} for support.")
            return
    if status in {"replay", "duplicate"}:
        await message.answer("This payment was already processed. Use /purchases to download.")
        return
    log.warning("Rejected successful payment for user %s", message.from_user.id)
    await message.answer(f"Payment validation failed. Contact @{SUPPORT_HANDLE} for support.")


@dp.message(Command("paysupport"))
async def support(message: Message) -> None:
    await message.answer(f"Payment support: @{SUPPORT_HANDLE}")


@dp.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    if is_admin_private(message):
        await message.answer(
            "Send an MP3 as audio with its title in the caption. It will be published automatically. /stats /balance"
        )


@dp.message(Command("stats"))
async def stats(message: Message) -> None:
    if is_admin_private(message):
        sales = db.execute("SELECT count(*) FROM orders WHERE paid=1").fetchone()[0]
        await message.answer(f"Sales: {sales} | Gross: {sales * PRICE_STARS} Stars")


@dp.message(Command("balance", "revenue"))
async def balance(message: Message) -> None:
    """Show Telegram's authoritative bot balance to the private admin."""
    if not is_admin_private(message):
        return
    try:
        star_balance = await bot.get_my_star_balance()
    except Exception:
        log.exception("Could not read Telegram Stars balance")
        await message.answer("Could not read the Telegram Stars balance right now.")
        return
    sales = db.execute("SELECT count(*) FROM orders WHERE paid=1").fetchone()[0]
    await message.answer(
        "Telegram bot balance: "
        f"{star_balance.amount} Stars\n"
        f"Recorded paid orders: {sales}\n"
        f"Recorded gross at current price: {sales * PRICE_STARS} Stars\n\n"
        "For lifetime proceeds and withdrawal status, open the bot's Monetization / Stars Balance screen in Telegram."
    )


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
                INSERT INTO tracks(title, description, campaign, cover, full, preview, preview_video, hash)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    (message.caption or audio.title or "Untitled")[:120],
                    "",
                    "",
                    None,
                    str(full),
                    str(preview),
                    None,
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
