# Hinglish SRT Subtitle Translator Bot

A professional Telegram bot that translates English `.srt` subtitle files into natural Hinglish (Roman script) and sends the translated file back to the user.

---

## Features

- Upload any `.srt` file — get a Hinglish-translated `.srt` back
- Three translation modes: `normal`, `anime_dub`, `casual`
- Optional AI-powered translation via OpenAI GPT-4o-mini
- Built-in dummy translator for testing (no API key required)
- Fully async, modular, production-ready code

---

## Project Structure

```
telegram-bot/
├── bot.py            # Entry point — initializes bot, registers handlers
├── handlers.py       # Telegram command & message handlers
├── srt_parser.py     # SRT parser and rebuilder
├── translator.py     # Pluggable translator (DummyTranslator / OpenAITranslator)
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md         # This file
```

---

## Quick Start

### 1. Clone / download the files

```bash
git clone <your-repo>
cd telegram-bot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

```env
BOT_TOKEN=your_telegram_bot_token_here
```

To enable AI translation, also set:

```env
TRANSLATOR=openai
OPENAI_API_KEY=your_openai_api_key_here
```

### 4. Run the bot

```bash
python bot.py
```

---

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Usage instructions |
| `/mode <mode>` | Set translation mode (`normal`, `anime_dub`, `casual`) |
| `/sample` | Show a sample English → Hinglish translation |

---

## Translation Modes

| Mode | Style |
|---|---|
| `normal` | Everyday natural Hinglish — suitable for any movie/show |
| `anime_dub` | Energetic, expressive — tailored for anime dubbing |
| `casual` | Street-style, slang-heavy, very informal |

---

## Deployment

### On a VPS (e.g. Ubuntu)

```bash
# Install Python 3.11+
sudo apt install python3.11 python3.11-venv -y

# Set up the project
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure env
cp .env.example .env && nano .env

# Run with systemd or screen
screen -S hinglish-bot
python bot.py
# Ctrl+A, D to detach
```

### On Render

1. Create a new **Background Worker** service.
2. Set **Build Command**: `pip install -r requirements.txt`
3. Set **Start Command**: `python bot.py`
4. Add environment variables (`BOT_TOKEN`, optionally `OPENAI_API_KEY`, `TRANSLATOR`) in the Render dashboard.

### On Heroku

```bash
heroku create
heroku config:set BOT_TOKEN=your_token_here
heroku config:set TRANSLATOR=openai
heroku config:set OPENAI_API_KEY=your_key_here
git push heroku main
heroku ps:scale worker=1
```

Create a `Procfile`:
```
worker: python bot.py
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ Yes | — | Telegram bot token from @BotFather |
| `TRANSLATOR` | No | `dummy` | `openai` or `dummy` |
| `OPENAI_API_KEY` | Only if `TRANSLATOR=openai` | — | OpenAI API key |
| `MAX_FILE_SIZE_MB` | No | `5` | Max upload size in MB |

---

## Extending the Translator

To plug in your own translation backend (DeepL, Google Translate, etc.):

1. Open `translator.py`
2. Create a new class extending `BaseTranslator`
3. Implement the `translate(self, text: str) -> str` method
4. Update `get_translator()` to return your new class

---

## Translation Style Examples

| English | Hinglish |
|---|---|
| I can't lose here. | Main yahan haar nahi sakta. |
| Let's go! | Chalo, let's go! |
| You idiot! | Tum idiot ho kya! |
| I'll protect everyone. | Main sabko protect karunga. |
