"""
Translation module — pluggable translator architecture.

Translators (auto-selected by priority):
  1. GroqTranslator   — FREE, ultra-fast (Llama 3.1) — recommended
  2. GeminiTranslator — FREE, Google Gemini
  3. OpenAITranslator — paid, GPT-4o-mini
  4. DummyTranslator  — testing only, no API key needed

You can force a specific translator via TRANSLATOR=groq|gemini|openai|dummy.
"""

import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Translation modes
# ---------------------------------------------------------------------------
MODE_PROMPTS: dict[str, str] = {
    "anime_dub": (
        "You are a professional Hindi anime dubbing scriptwriter — like the writers behind "
        "Naruto, Dragon Ball Z, One Piece, and Demon Slayer dubbed on Hungama TV and Disney+ Hotstar India.\n\n"
        "Your job: Convert subtitle dialogue from ANY language into natural, expressive HINDI written in Roman script "
        "(NOT Devanagari script). This is for use as dubbed anime subtitles.\n\n"
        "STRICT RULES:\n"
        "1. Write in pure, natural spoken Hindi using Roman script (e.g. 'Main yahan nahi aana chahta tha').\n"
        "2. NEVER use Devanagari characters. Only Roman/Latin letters.\n"
        "3. Keep ALL of these UNCHANGED: character names, place names, attack/technique names "
        "   (e.g. Rasengan, Kamehameha, Bankai, Sharingan), Japanese honorifics (sensei, senpai, kun, chan, sama).\n"
        "4. Match the emotional intensity exactly:\n"
        "   - Battle cries: short, powerful, punchy ('Nahi! Main harna nahi dunga!')\n"
        "   - Emotional moments: deep, heartfelt ('Tum meri zindagi mein sabse khaas ho')\n"
        "   - Comedy: light and fun ('Arre yaar, yeh kya ho gaya?')\n"
        "   - Villains: cold, menacing ('Tumhara ant ab nikat hai')\n"
        "5. Use natural Hindi spoken expressions:\n"
        "   - I → Main\n"
        "   - You → Tum / Tu / Aap (match the formality of the scene)\n"
        "   - We → Hum\n"
        "   - No! → Nahi! / Bilkul nahi!\n"
        "   - Yes! → Haan! / Zaroor!\n"
        "   - Why? → Kyun? / Aakhir kyun?\n"
        "   - How? → Kaise? / Yeh kaise mumkin hai?\n"
        "   - What? → Kya? / Yeh kya hai?\n"
        "   - Impossible! → Yeh nahi ho sakta! / Asambhav!\n"
        "   - Let's go! → Chalo! / Ab chalte hain!\n"
        "   - I won't give up! → Main haar nahi maanunga!\n"
        "   - I'll protect everyone! → Main sabki raksha karunga!\n"
        "   - My power! → Meri shakti!\n"
        "   - This is my resolve! → Yahi mera sankalp hai!\n"
        "6. Do NOT mix English words unless they are proper nouns or attack names.\n"
        "7. Keep translated dialogue similar in length to the original — short lines stay short.\n"
        "8. Preserve ALL newlines exactly as they appear inside each subtitle block.\n"
        "9. Output ONLY the translated subtitle text — no explanations, no labels, nothing extra."
    ),
    "normal": (
        "You are an expert Hinglish subtitle translator. "
        "Convert subtitle text from ANY language into natural Hinglish written in Roman script (NOT Devanagari). "
        "Guidelines:\n"
        "- Detect the source language automatically.\n"
        "- Use everyday spoken Hindi freely mixed with common English words.\n"
        "- Keep character names, anime terms, power names, honorifics, and branded terms unchanged.\n"
        "- Preserve the emotional tone — be expressive where needed.\n"
        "- Do NOT translate line-by-line robotically; produce natural flowing Hinglish.\n"
        "- Preserve newlines inside each block exactly as they appear.\n"
        "- Output only the translated subtitle text, nothing else."
    ),
    "casual": (
        "You are a cool, laid-back Hinglish subtitle translator. "
        "Convert subtitle text from ANY language into super casual, street-style Hinglish in Roman script (NOT Devanagari). "
        "Guidelines:\n"
        "- Detect the source language automatically.\n"
        "- Sound like a young Indian person chatting with friends.\n"
        "- Use slang and filler words (yaar, bhai, arre, bro) where natural.\n"
        "- Keep English words Indians commonly use (okay, cool, seriously, anyway).\n"
        "- Do NOT sound formal or bookish.\n"
        "- Preserve newlines inside each block exactly as they appear.\n"
        "- Output only the translated subtitle text, nothing else."
    ),
}

DEFAULT_MODE = "anime_dub"

BATCH_SIZE = int(os.environ.get("TRANSLATE_BATCH_SIZE", "20"))
BATCH_DELAY = float(os.environ.get("TRANSLATE_BATCH_DELAY", "0.3"))

ProgressCallback = Optional[Callable[[int, int], None]]


# ---------------------------------------------------------------------------
# Batch prompt helpers (shared by all AI translators)
# ---------------------------------------------------------------------------
_BLOCK_SEP_PATTERN = re.compile(r"<<<BLOCK_(\d+)>>>")


def _build_batch_prompt(texts: List[str]) -> str:
    parts = []
    for i, text in enumerate(texts):
        parts.append(f"<<<BLOCK_{i}>>>\n{text}")
    return "\n\n".join(parts)


def _parse_batch_response(
    response_text: str, expected_count: int, originals: List[str]
) -> List[str]:
    results: List[Optional[str]] = [None] * expected_count
    segments = _BLOCK_SEP_PATTERN.split(response_text)
    i = 1
    while i + 1 < len(segments):
        try:
            idx = int(segments[i].strip())
            content = segments[i + 1].strip()
            if 0 <= idx < expected_count:
                results[idx] = content
        except (ValueError, IndexError):
            pass
        i += 2
    for idx in range(expected_count):
        if results[idx] is None:
            logger.warning("Missing batch response for block %d, keeping original", idx)
            results[idx] = originals[idx]
    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class BaseTranslator(ABC):
    def __init__(self, mode: str = DEFAULT_MODE):
        self.mode = mode if mode in MODE_PROMPTS else DEFAULT_MODE

    @abstractmethod
    def translate(self, text: str) -> str:
        pass

    def translate_batch(
        self,
        texts: List[str],
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        total = len(texts)
        results: List[str] = []
        for i, text in enumerate(texts):
            results.append(self.translate(text))
            if progress_callback:
                progress_callback(i + 1, total)
        return results


# ---------------------------------------------------------------------------
# Dummy translator
# ---------------------------------------------------------------------------
_DUMMY_REPLACEMENTS = [
    (r"\bI can't\b", "Main nahi kar sakta"),
    (r"\bI won't\b", "Main nahi karunga"),
    (r"\bI will\b", "Main karunga"),
    (r"\bLet's go\b", "Chalo, let's go"),
    (r"\bYou idiot\b", "Tum idiot ho"),
    (r"\beveryone\b", "sabko"),
    (r"\bfriend\b", "dost"),
    (r"\bWait\b", "Ruko"),
    (r"\bNo way\b", "Bilkul nahi"),
    (r"\bThank you\b", "Shukriya"),
    (r"\bSorry\b", "Maafi"),
    (r"\bOkay\b", "Theek hai"),
    (r"\bYes\b", "Haan"),
    (r"\bNo\b", "Nahi"),
]
_COMPILED_DUMMY = [
    (re.compile(pat, re.IGNORECASE), repl) for pat, repl in _DUMMY_REPLACEMENTS
]


class DummyTranslator(BaseTranslator):
    def translate(self, text: str) -> str:
        result = text
        for pattern, replacement in _COMPILED_DUMMY:
            result = pattern.sub(replacement, result)
        return result

    def translate_batch(
        self,
        texts: List[str],
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        total = len(texts)
        results = []
        for i, text in enumerate(texts):
            results.append(self.translate(text))
            if progress_callback:
                progress_callback(i + 1, total)
        return results


# ---------------------------------------------------------------------------
# Shared batched translate_batch mixin for AI translators
# ---------------------------------------------------------------------------
class BatchedAITranslator(BaseTranslator):
    """
    Handles chunking + progress for any AI translator.
    Subclasses only need to implement _translate_texts(texts) → List[str].
    """

    def translate(self, text: str) -> str:
        return self._translate_texts([text])[0]

    def _translate_texts(self, texts: List[str]) -> List[str]:
        raise NotImplementedError

    def translate_batch(
        self,
        texts: List[str],
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        total = len(texts)
        results: List[str] = []
        done = 0
        for chunk_start in range(0, total, BATCH_SIZE):
            chunk = texts[chunk_start: chunk_start + BATCH_SIZE]
            chunk_results = self._translate_texts(chunk)
            results.extend(chunk_results)
            done += len(chunk)
            if progress_callback:
                progress_callback(done, total)
            if done < total and BATCH_DELAY > 0:
                time.sleep(BATCH_DELAY)
        return results


# ---------------------------------------------------------------------------
# Gemini Translator — FREE tier (recommended)
# ---------------------------------------------------------------------------
class GeminiTranslator(BatchedAITranslator):
    """
    Uses Google Gemini API (FREE tier available).
    Get a free API key at: https://aistudio.google.com/app/apikey
    Set GEMINI_API_KEY in your .env file.
    Free limits: 15 requests/min, 1500 requests/day — plenty for subtitles.
    """

    def __init__(self, mode: str = DEFAULT_MODE):
        super().__init__(mode)
        try:
            from google import genai  # type: ignore
            from google.genai import types as genai_types  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "google-genai package is not installed. Run: pip install google-genai"
            ) from exc

        api_key = os.environ.get("AIzaSyDSKCgVpBi6I9xR48pMDeCPqD4jaCx6DnA")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set.")

        self._client = genai.Client(api_key=api_key)
        self._genai_types = genai_types
        self._system_prompt = (
            MODE_PROMPTS[self.mode]
            + "\n\nIMPORTANT: The input contains multiple subtitle blocks separated by "
            "<<<BLOCK_N>>> markers (where N is the block index starting from 0). "
            "Return ALL blocks translated, each preceded by its exact <<<BLOCK_N>>> marker. "
            "Do not merge or skip any blocks. Preserve internal newlines in each block."
        )

    def _translate_texts(self, texts: List[str]) -> List[str]:
        batch_input = _build_batch_prompt(texts)
        full_prompt = self._system_prompt + "\n\n" + batch_input
        try:
            response = self._client.models.generate_content(
                model="gemini-1.5-flash",
                contents=full_prompt,
                config=self._genai_types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )
            raw = response.text or ""
            return _parse_batch_response(raw, len(texts), texts)
        except Exception as exc:
            err = str(exc)
            if "quota" in err.lower() or "429" in err or "rate" in err.lower():
                raise RuntimeError(
                    "Gemini API rate limit ho gayi. Thodi der baad dobara try karo.\n"
                    "Free limit: 15 requests/minute. Agar zyada chahiye toh Google Cloud billing enable karo."
                ) from exc
            logger.exception("Gemini translation failed")
            return list(texts)


# ---------------------------------------------------------------------------
# OpenAI Translator — paid
# ---------------------------------------------------------------------------
class OpenAITranslator(BatchedAITranslator):
    """
    Uses OpenAI GPT-4o-mini. Requires billing on https://platform.openai.com
    """

    def __init__(self, mode: str = DEFAULT_MODE):
        super().__init__(mode)
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise RuntimeError("openai package is not installed.") from exc

        api_key = os.environ.get("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")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        self._client = OpenAI(api_key=api_key)
        self._system_prompt = (
            MODE_PROMPTS[self.mode]
            + "\n\nIMPORTANT: The input contains multiple subtitle blocks separated by "
            "<<<BLOCK_N>>> markers (where N is the block index starting from 0). "
            "Return ALL blocks translated, each preceded by its exact <<<BLOCK_N>>> marker. "
            "Do not merge or skip any blocks. Preserve internal newlines in each block."
        )

    def _translate_texts(self, texts: List[str]) -> List[str]:
        batch_input = _build_batch_prompt(texts)
        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": batch_input},
                ],
                temperature=0.7,
                max_tokens=4096,
            )
            raw = response.choices[0].message.content or ""
            return _parse_batch_response(raw, len(texts), texts)
        except Exception as exc:
            err = str(exc)
            if "insufficient_quota" in err or "429" in err:
                raise RuntimeError(
                    "OpenAI API quota khatam ho gayi hai. "
                    "Billing check karo: https://platform.openai.com/usage\n\n"
                    "💡 *Free alternative:* GEMINI_API_KEY set karo — Google Gemini bilkul free hai!\n"
                    "Key milegi yahan: https://aistudio.google.com/app/apikey"
                ) from exc
            logger.exception("OpenAI translation failed")
            return list(texts)


# ---------------------------------------------------------------------------
# Groq Translator — FREE, ultra-fast (recommended)
# ---------------------------------------------------------------------------
class GroqTranslator(BatchedAITranslator):
    """
    Uses Groq API with Llama 3 — extremely fast and FREE tier available.
    Get a free API key at: https://console.groq.com/keys
    Free limits: very generous — ideal for subtitle translation.
    """

    def __init__(self, mode: str = DEFAULT_MODE):
        super().__init__(mode)
        try:
            from groq import Groq  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "groq package is not installed. Run: pip install groq"
            ) from exc

        api_key = os.environ.get("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")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable is not set.")

        self._client = Groq(api_key=api_key)
        self._system_prompt = (
            MODE_PROMPTS[self.mode]
            + "\n\nIMPORTANT: The input contains multiple subtitle blocks separated by "
            "<<<BLOCK_N>>> markers (where N is the block index starting from 0). "
            "Return ALL blocks translated, each preceded by its exact <<<BLOCK_N>>> marker. "
            "Do not merge or skip any blocks. Preserve internal newlines in each block."
        )

    def _translate_texts(self, texts: List[str]) -> List[str]:
        batch_input = _build_batch_prompt(texts)
        try:
            response = self._client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": batch_input},
                ],
                temperature=0.7,
                max_tokens=8192,
            )
            raw = response.choices[0].message.content or ""
            return _parse_batch_response(raw, len(texts), texts)
        except Exception as exc:
            err = str(exc)
            if "rate_limit" in err.lower() or "429" in err:
                raise RuntimeError(
                    "Groq API rate limit ho gayi. Thodi der baad dobara try karo.\n"
                    "Free tier pe limits hain — ek minute baad phir try karo."
                ) from exc
            logger.exception("Groq translation failed")
            return list(texts)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_translator(mode: str = DEFAULT_MODE) -> BaseTranslator:
    """
    Auto-select the best available translator.
    Priority: TRANSLATOR env override → Groq → Gemini → OpenAI → Dummy
    """
    forced = os.environ.get("TRANSLATOR", "").lower()

    if forced == "groq" or (not forced and os.environ.get("GROQ_API_KEY")):
        logger.info("Using GroqTranslator in mode: %s", mode)
        return GroqTranslator(mode=mode)

    if forced == "gemini" or (not forced and os.environ.get("GEMINI_API_KEY")):
        logger.info("Using GeminiTranslator in mode: %s", mode)
        return GeminiTranslator(mode=mode)

    if forced == "openai" or (not forced and os.environ.get("OPENAI_API_KEY")):
        logger.info("Using OpenAITranslator in mode: %s", mode)
        return OpenAITranslator(mode=mode)

    logger.info("Using DummyTranslator in mode: %s (no API key found)", mode)
    return DummyTranslator(mode=mode)
