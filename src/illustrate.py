"""Cover-image generation via Draw Things' local HTTP API (A1111-compatible).

Flow: ask the LLM for a short English *scene* describing the day's theme → append
a fixed per-category style suffix (brand consistency) → POST to Draw Things
txt2img → return PNG bytes. Everything is best-effort: any failure (Draw Things
off, timeout, empty prompt) logs a warning and returns None so the digest still
publishes without an image.
"""

from __future__ import annotations

import base64
import logging
import random

import httpx

from . import config
from .models import Item
from .summarize import Summarizer

logger = logging.getLogger(__name__)


IMAGE_SYSTEM_PROMPT = """You are an art director writing prompts for a text-to-image model.
Given today's top headlines, output ONE concise English image prompt describing a single
clean, modern editorial COVER illustration that captures the overall theme or a visual metaphor.

Rules:
- Describe only the scene/subject/mood (objects, composition, mood). 12-30 words.
- Aesthetic must feel CONTEMPORARY (2025): sleek, abstract, minimal.
- BANNED (never use): retro / vintage / dated looks; CRT or boxy monitors, old beige computers;
  steam trains or locomotives; gears or cogwheels; light bulbs; robots; human brains; circuit-board
  clichés; anything that looks from the 1990s-2000s.
- Prefer ABSTRACT concepts and shapes over literal devices. When you must show technology, depict
  it as sleek modern glass/holographic/geometric forms, not physical gadgets.
- Absolutely NO text, words, letters or numbers in the image.
- Do not name real companies, logos or real people.
- Output ONLY the prompt, no quotes, no explanation, no style adjectives about rendering."""


def _theme_text(picks: list[Item]) -> str:
    heads = [p.title for p in picks[:5]]
    return "Top headlines today:\n- " + "\n- ".join(heads)


def build_prompt(picks: list[Item], category: str, summarizer: Summarizer) -> str | None:
    try:
        scene = summarizer.chat(IMAGE_SYSTEM_PROMPT, _theme_text(picks), temperature=0.8).strip()
    except Exception as exc:
        logger.warning("cover: prompt generation failed: %s", exc)
        return None
    scene = scene.strip().strip('"').strip().rstrip(".,;:、，。 ")
    if not scene:
        return None
    suffix = config.COVER_STYLE_SUFFIX.get(category, "")
    return f"{scene}, {suffix}" if suffix else scene


def generate(prompt: str) -> bytes | None:
    """POST to Draw Things txt2img; return PNG bytes, or None if unreachable/failed."""
    body = {
        "prompt": prompt,
        "negative_prompt": config.COVER_NEGATIVE_PROMPT,
        "width": config.COVER_WIDTH,
        "height": config.COVER_HEIGHT,
        "steps": config.COVER_STEPS,
        "seed": random.randint(0, 2**31 - 1),
    }
    try:
        with httpx.Client(timeout=config.COVER_TIMEOUT_SECONDS) as client:
            response = client.post(config.DRAWTHINGS_ENDPOINT, json=body)
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError:
        logger.warning("cover: Draw Things not reachable at %s — is the API Server on? "
                       "skipping image.", config.DRAWTHINGS_ENDPOINT)
        return None
    except Exception as exc:
        logger.warning("cover: generation failed: %s", exc)
        return None

    images = data.get("images") or []
    if not images:
        logger.warning("cover: Draw Things returned no image")
        return None
    b64 = images[0]
    if "," in b64 and b64.strip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        return base64.b64decode(b64)
    except Exception as exc:
        logger.warning("cover: bad base64 from Draw Things: %s", exc)
        return None


def make_cover(picks: list[Item], category: str, summarizer: Summarizer) -> bytes | None:
    """Build a prompt and render it. Returns PNG bytes or None (best-effort)."""
    prompt = build_prompt(picks, category, summarizer)
    if not prompt:
        logger.info("cover: no prompt (provider=none or empty); skipping image")
        return None
    logger.info("cover: prompt = %s", prompt)
    return generate(prompt)


def to_data_uri(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
