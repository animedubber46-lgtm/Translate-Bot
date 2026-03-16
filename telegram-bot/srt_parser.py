"""
SRT parser and rebuilder.

An SRT file has repeating blocks separated by blank lines:
    <index>
    <start> --> <end>
    <dialogue line(s)>
    (blank line)

This module parses those blocks and rebuilds a valid SRT from translated text.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

_BLOCK_SEPARATOR = re.compile(r"\r?\n\r?\n")
_TIMECODE_LINE = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


@dataclass
class SRTBlock:
    index: str
    timecode: str
    lines: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class SRTParseError(ValueError):
    pass


def parse_srt(content: str) -> List[SRTBlock]:
    """
    Parse an SRT file string into a list of SRTBlock objects.
    Raises SRTParseError if the content does not look like a valid SRT file.
    """
    content = content.strip()
    raw_blocks = _BLOCK_SEPARATOR.split(content)

    blocks: List[SRTBlock] = []
    for raw in raw_blocks:
        raw = raw.strip()
        if not raw:
            continue

        block_lines = raw.splitlines()
        if len(block_lines) < 2:
            logger.warning("Skipping malformed SRT block: %r", raw)
            continue

        index_line = block_lines[0].strip()
        timecode_line = block_lines[1].strip()

        if not index_line.isdigit():
            logger.warning("Block does not start with an integer index, skipping: %r", index_line)
            continue

        if not _TIMECODE_LINE.match(timecode_line):
            logger.warning("Second line is not a valid timecode, skipping block %s", index_line)
            continue

        dialogue_lines = [l for l in block_lines[2:]]

        blocks.append(SRTBlock(
            index=index_line,
            timecode=timecode_line,
            lines=dialogue_lines,
        ))

    if not blocks:
        raise SRTParseError("No valid SRT blocks found. Is this a valid .srt file?")

    logger.info("Parsed %d SRT blocks", len(blocks))
    return blocks


def rebuild_srt(blocks: List[SRTBlock], translated_texts: List[str]) -> str:
    """
    Reconstruct a valid SRT string from parsed blocks and translated texts.
    Indices and timecodes are preserved exactly.
    """
    if len(blocks) != len(translated_texts):
        raise ValueError(
            f"Mismatch: {len(blocks)} blocks but {len(translated_texts)} translations"
        )

    output_parts: List[str] = []
    for block, translated in zip(blocks, translated_texts):
        translated = translated.strip()
        output_parts.append(f"{block.index}\n{block.timecode}\n{translated}")

    return "\n\n".join(output_parts) + "\n"
