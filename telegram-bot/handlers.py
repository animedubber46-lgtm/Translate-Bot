"""
Telegram bot handlers — one async function per command / message type.
"""

import asyncio
import concurrent.futures
import logging
import os
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from srt_parser import parse_srt, rebuild_srt, SRTParseError
from translator import get_translator, MODE_PROMPTS
from premium import is_owner, is_premium, grant_premium, get_expiry, list_premium_users, OWNER_ID

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "5"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

VALID_MODES = list(MODE_PROMPTS.keys())
DEFAULT_MODE = "anime_dub"

QR_IMAGE_PATH = Path(__file__).parent / "payment_qr.png"

_user_modes: dict[int, str] = {}

PROGRESS_UPDATE_EVERY = 10

MAX_CONCURRENT_TASKS = 10
_active_tasks: int = 0


def _get_user_mode(user_id: int) -> str:
    return _user_modes.get(user_id, DEFAULT_MODE)


def _progress_bar(done: int, total: int, width: int = 20) -> str:
    filled = int(width * done / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * done / total) if total else 0
    return f"[{bar}] {pct}%"


def _premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Premium Lena Hai? Yahan Click Karo!", callback_data="show_premium")]
    ])


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    name = user.first_name if user else "yodha"

    if is_owner(user_id) or is_premium(user_id):
        expiry = get_expiry(user_id)
        expiry_text = ""
        if expiry and not is_owner(user_id):
            expiry_text = f"\n⏳ Premium expires: *{expiry.strftime('%d %b %Y')}*"

        await update.message.reply_text(
            f"Namaste {name}! ⚔️🎌\n\n"
            "Main hoon aapka *Anime Hindi Dub Subtitle Bot!*\n\n"
            "Kisi bhi anime ki .srt subtitle file bhejiye — "
            "main use bilkul Hindi dubbed anime jaisi language mein translate karunga! 🇮🇳\n\n"
            "📺 Naruto, Dragon Ball, One Piece, Demon Slayer — sab ke liye ready!\n"
            + expiry_text +
            "\n\nSeedha apni .srt file bhejo, ya /help dekho.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"Namaste {name}! ⚔️🎌\n\n"
            "Main hoon *Anime Hindi Dub Subtitle Bot!*\n\n"
            "Yeh bot *Premium users* ke liye hai.\n\n"
            "💎 *Premium Plan: ₹50/month*\n"
            "✅ Unlimited subtitle translation\n"
            "✅ Anime Hindi dub quality\n"
            "✅ All modes (anime_dub, normal, casual)\n"
            "✅ Fast Groq AI translation\n\n"
            "Premium lene ke liye neeche button dabao 👇",
            parse_mode="Markdown",
            reply_markup=_premium_keyboard(),
        )


# ---------------------------------------------------------------------------
# Inline button callback — show premium payment info
# ---------------------------------------------------------------------------
async def premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "show_premium":
        caption = (
            "💎 *Premium Plan — ₹50/month*\n\n"
            "UPI par payment karo aur screenshot owner ko bhejo.\n\n"
            "📲 *UPI ID:* `shivam.animes@ptyes`\n\n"
            "Payment ke baad contact karo:\n"
            "👑 *Owner:* @Lord\_Shri\_Ram\n\n"
            "_Premium milne ke baad bot seedha use kar sakte ho!_"
        )
        if QR_IMAGE_PATH.exists():
            await query.message.reply_photo(
                photo=open(QR_IMAGE_PATH, "rb"),
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            await query.message.reply_text(caption, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_premium(user_id):
        await update.message.reply_text(
            "❌ Yeh command sirf Premium users ke liye hai.\n\n"
            "Premium lene ke liye /start karo.",
            reply_markup=_premium_keyboard(),
        )
        return

    await update.message.reply_text(
        "📖 *Bot kaise use karein:*\n\n"
        "1. Apni anime ki `.srt` file bhejo (kisi bhi language mein)\n"
        "2. Bot file download karega aur Hindi dub style mein translate karega\n"
        "3. Translation ka real-time progress dikhega\n"
        "4. Translated `.srt` file wapas milegi — seedha use karo!\n\n"
        "📌 *Commands:*\n"
        "/start — Welcome\n"
        "/help — Yeh instructions\n"
        "/mode — Translation style dekho ya change karo\n"
        "/sample — Example translation dekho\n"
        "/mystatus — Apna premium status dekho\n\n"
        "🎭 *Translation Modes:*\n"
        "`anime_dub` ⭐ — Pure Hindi, anime dub style (DEFAULT)\n"
        "`normal` — Hinglish (Hindi + English mix)\n"
        "`casual` — Casual street-style Hinglish\n\n"
        f"📁 *Max file size:* {MAX_FILE_SIZE_MB} MB\n"
        "🌍 *Source language:* Automatic detection (Japanese, English, Korean, etc.)",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /mystatus — user checks own premium status
# ---------------------------------------------------------------------------
async def mystatus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if is_owner(user_id):
        await update.message.reply_text("👑 Aap *Bot Owner* hain — unlimited free access!", parse_mode="Markdown")
        return

    if is_premium(user_id):
        expiry = get_expiry(user_id)
        expiry_text = expiry.strftime("%d %b %Y") if expiry else "Unknown"
        await update.message.reply_text(
            f"✅ Aapka *Premium active* hai!\n\n⏳ Expires: *{expiry_text}*",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ Aapke paas Premium nahi hai.\n\nPremium lene ke liye:",
            reply_markup=_premium_keyboard(),
        )


# ---------------------------------------------------------------------------
# /p1 <user_id>  and  /p2 <user_id>  — Owner only: grant premium
# ---------------------------------------------------------------------------
async def grant_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Yeh command sirf owner ke liye hai.")
        return

    command = update.message.text.split()[0].lstrip("/").lower()
    months = 1 if command == "p1" else 2

    if not context.args:
        await update.message.reply_text(
            f"❌ User ID nahi diya!\n\nUsage: `/{command} <user_id>`",
            parse_mode="Markdown",
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Sirf numbers dalo.")
        return

    expiry = grant_premium(target_id, months)
    expiry_str = expiry.strftime("%d %b %Y")

    await update.message.reply_text(
        f"✅ *Premium diya gaya!*\n\n"
        f"👤 User ID: `{target_id}`\n"
        f"📅 Duration: *{months} month(s)*\n"
        f"⏳ Expires: *{expiry_str}*\n\n"
        f"User ab bot use kar sakta hai!",
        parse_mode="Markdown",
    )

    # Notify the user
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 *Aapko Premium mil gaya!*\n\n"
                f"📅 Duration: *{months} month(s)*\n"
                f"⏳ Valid till: *{expiry_str}*\n\n"
                "Ab seedha apni .srt file bhejo aur translate karo! ⚔️🎌"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Could not notify user %d about premium grant", target_id)


# ---------------------------------------------------------------------------
# /listpremium — Owner only: see all active premium users
# ---------------------------------------------------------------------------
async def listpremium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Yeh command sirf owner ke liye hai.")
        return

    users = list_premium_users()
    if not users:
        await update.message.reply_text("📋 Abhi koi active premium user nahi hai.")
        return

    lines = "\n".join(f"`{uid}` — expires *{exp.strftime('%d %b %Y')}*" for uid, exp in users)
    await update.message.reply_text(
        f"📋 *Active Premium Users ({len(users)}):*\n\n" + lines,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /mode
# ---------------------------------------------------------------------------
async def mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_premium(user_id):
        await update.message.reply_text(
            "❌ Yeh command sirf Premium users ke liye hai.",
            reply_markup=_premium_keyboard(),
        )
        return

    args = context.args

    if not args:
        current = _get_user_mode(user_id)
        await update.message.reply_text(
            f"🎭 Abhi ka mode: *{current}*\n\n"
            "Mode change karne ke liye:\n\n"
            "`/mode anime_dub` ⭐ — Pure Hindi, anime dub style (DEFAULT)\n"
            "   → Naruto, DBZ, One Piece jaisi dubbed Hindi\n\n"
            "`/mode normal` — Hinglish (Hindi + English mix)\n"
            "   → Everyday Indian spoken style\n\n"
            "`/mode casual` — Casual street Hinglish\n"
            "   → Yaar/bhai/arre wali baat",
            parse_mode="Markdown",
        )
        return

    requested_mode = args[0].lower()
    if requested_mode not in VALID_MODES:
        await update.message.reply_text(
            f"❌ Invalid mode: `{requested_mode}`\n\n"
            f"Valid modes hain: {', '.join(VALID_MODES)}",
            parse_mode="Markdown",
        )
        return

    _user_modes[user_id] = requested_mode
    await update.message.reply_text(
        f"✅ Mode set to *{requested_mode}*!\n\n"
        "Ab aapki agali file is mode mein translate hogi.",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /sample
# ---------------------------------------------------------------------------
SAMPLE_LINES = [
    ("I can't lose here!", "Main yahan haar nahi sakta!"),
    ("Let's go!", "Chalo!"),
    ("You idiot!", "Bewakoof kahin ke!"),
    ("I'll protect everyone.", "Main sabki raksha karunga."),
    ("This power... it's mine!", "Yeh shakti... yeh meri hai!"),
    ("I won't give up, no matter what!", "Main kabhee haar nahi maanunga, chahe kuch bhi ho!"),
    ("Impossible! How is he this strong?!", "Asambhav! Yeh itna taqatwar kaise ho sakta hai?!"),
    ("Sensei, thank you for everything.", "Sensei, aapka bahut shukriya."),
]


async def sample_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = "\n".join(
        f"*EN:* `{en}`\n*HI:* `{hi}`"
        for en, hi in SAMPLE_LINES
    )
    await update.message.reply_text(
        "📝 *Sample — Anime Hindi Dub Style:*\n\n"
        + lines
        + "\n\n_Mode: anime\\_dub (default)_",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Document handler (main flow)
# ---------------------------------------------------------------------------
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _active_tasks
    message = update.message
    document = message.document
    user_id = update.effective_user.id

    # --- Premium check ---
    if not is_owner(user_id) and not is_premium(user_id):
        await message.reply_text(
            "❌ *Yeh bot sirf Premium users ke liye hai!*\n\n"
            "💎 *Premium Plan: ₹50/month*\n\n"
            "Premium lene ke liye neeche button dabao 👇",
            parse_mode="Markdown",
            reply_markup=_premium_keyboard(),
        )
        return

    # --- Queue / concurrency limit check ---
    if _active_tasks >= MAX_CONCURRENT_TASKS:
        await message.reply_text(
            "⏳ *Queue Full!*\n\n"
            f"Abhi *{_active_tasks}/{MAX_CONCURRENT_TASKS}* users ki files translate ho rahi hain.\n\n"
            "Thoda wait karo aur 2-3 minutes baad dobara bhejo. 🙏",
            parse_mode="Markdown",
        )
        return

    # --- Validate file extension ---
    file_name = document.file_name or ""
    if not file_name.lower().endswith(".srt"):
        await message.reply_text(
            "❌ Sirf `.srt` files accept ki jaati hain.\n"
            "Please ek valid subtitle file bhejo."
        )
        return

    # --- Validate file size ---
    if document.file_size and document.file_size > MAX_FILE_SIZE_BYTES:
        await message.reply_text(
            f"❌ File bahut badi hai! Maximum allowed size {MAX_FILE_SIZE_MB} MB hai.\n"
            "Chhoti file bhejo please."
        )
        return

    status_msg: Message = await message.reply_text("📥 File mil gayi! Downloading...")

    _active_tasks += 1
    try:
        tg_file = await context.bot.get_file(document.file_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / file_name
            output_name = Path(file_name).stem + "_hindi_dub.srt"
            output_path = Path(tmpdir) / output_name

            await tg_file.download_to_drive(str(input_path))
            logger.info("Downloaded file: %s (%d bytes)", file_name, input_path.stat().st_size)

            await _safe_edit(status_msg, "📂 File download ho gayi! Parsing kar raha hoon...")

            try:
                raw_content = input_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw_content = input_path.read_text(encoding="latin-1")

            try:
                blocks = parse_srt(raw_content)
            except SRTParseError as e:
                await _safe_edit(
                    status_msg,
                    f"❌ File parse nahi hui: {e}\n\nKya yeh ek valid .srt file hai?"
                )
                return

            total_blocks = len(blocks)
            mode = _get_user_mode(user_id)
            translator = get_translator(mode=mode)

            await _safe_edit(
                status_msg,
                f"🔄 Translation shuru ho rahi hai...\n\n"
                f"📊 Total blocks: *{total_blocks}*\n"
                f"🎭 Mode: *{mode}*\n\n"
                f"{_progress_bar(0, total_blocks)} 0/{total_blocks}",
                parse_mode="Markdown",
            )

            texts = [block.text for block in blocks]
            translated_texts: list[str] = []
            translation_error: str | None = None

            loop = asyncio.get_event_loop()
            last_reported = [0]

            async def update_progress(done: int, total: int) -> None:
                if done < total and done - last_reported[0] < PROGRESS_UPDATE_EVERY:
                    return
                last_reported[0] = done
                bar = _progress_bar(done, total)
                await _safe_edit(
                    status_msg,
                    f"🔄 Translation chal rahi hai...\n\n"
                    f"📊 Blocks: *{done}/{total}*\n"
                    f"🎭 Mode: *{mode}*\n\n"
                    f"{bar}",
                    parse_mode="Markdown",
                )

            progress_events: list[tuple[int, int]] = []

            def sync_progress_callback(done: int, total: int) -> None:
                progress_events.append((done, total))

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = loop.run_in_executor(
                executor,
                lambda: translator.translate_batch(texts, sync_progress_callback),
            )

            while not future.done():
                await asyncio.sleep(0.5)
                while progress_events:
                    done, total = progress_events.pop(0)
                    await update_progress(done, total)

            try:
                translated_texts = await future
            except RuntimeError as exc:
                translation_error = str(exc)
            except Exception as exc:
                logger.exception("Translation failed")
                translation_error = f"Translation mein unexpected error: {exc}"

            if translation_error:
                await _safe_edit(
                    status_msg,
                    f"❌ *Translation fail ho gayi!*\n\n{translation_error}",
                    parse_mode="Markdown",
                )
                return

            await _safe_edit(
                status_msg,
                f"✅ Translation complete!\n\n"
                f"📊 Blocks translated: *{total_blocks}/{total_blocks}*\n"
                f"{_progress_bar(total_blocks, total_blocks)}\n\n"
                "📤 File bhej raha hoon...",
                parse_mode="Markdown",
            )

            translated_srt = rebuild_srt(blocks, translated_texts)
            output_path.write_text(translated_srt, encoding="utf-8")
            logger.info("Sending translated file: %s", output_name)

            with open(output_path, "rb") as f:
                await message.reply_document(
                    document=f,
                    filename=output_name,
                    caption=(
                        "🎉 Yeh rahi aapki Hindi Dub translated subtitle file!\n"
                        f"🎭 Mode: *{mode}* | 📊 Blocks: *{total_blocks}*"
                    ),
                    parse_mode="Markdown",
                )

            await _safe_edit(status_msg, "✅ Done! File bhej di gayi. Enjoy karo! 🍿")

    except Exception as exc:
        logger.exception("Unexpected error in document_handler")
        await _safe_edit(
            status_msg,
            f"❌ Unexpected error aayi:\n`{exc}`\n\nPlease baad mein dobara try karo.",
            parse_mode="Markdown",
        )
    finally:
        _active_tasks -= 1


# ---------------------------------------------------------------------------
# Helper: edit a message safely
# ---------------------------------------------------------------------------
async def _safe_edit(
    msg: Message,
    text: str,
    parse_mode: str | None = None,
) -> None:
    try:
        await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as exc:
        err = str(exc)
        if "message is not modified" in err.lower():
            pass
        else:
            logger.warning("Could not edit message: %s", exc)
