"""Claude (Anthropic) integration - the LLM PLANNER brain.

Role: read a slide's Intermediate Representation (all content atoms with their
IDs, geometry and formatting) and return a LAYOUT PLAN that references atoms by
ID only. Claude decides *what goes where* (title/subtitle/bullets/columns/grid
funnels/etc.); it may never author text.

Safety: the returned plan is passed through verify.coverage() + validate_plan()
before use. If Claude invents an ID, drops content, or returns bad JSON, the plan
is rejected and the deterministic planner is used for that slide instead. So the
LLM can improve arrangement but can never fabricate or lose content.

Gated by ANTHROPIC_API_KEY; degrades safely to "unavailable" without a key.
"""
from __future__ import annotations

import json
import os

import requests

DEFAULT_MODEL = "claude-sonnet-4-5"    # overridable via ANTHROPIC_MODEL
_ENDPOINT = "https://api.anthropic.com/v1/messages"
_VERSION = "2023-06-01"

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV_LOADED = False


def _load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    path = os.path.join(_BACKEND_DIR, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


def _key():
    _load_env()
    return os.environ.get("ANTHROPIC_API_KEY")


def _model():
    _load_env()
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)


def available():
    return bool(_key())


def generate_json(system, user, max_tokens=4096, timeout=120, model=None):
    """Call Claude and parse a single JSON object/array from the reply.
    Returns parsed JSON, or None on any error (missing key, network, bad JSON)."""
    key = _key()
    if not key:
        return None
    payload = {
        "model": model or _model(),
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": _VERSION,
        "content-type": "application/json",
    }
    try:
        r = requests.post(_ENDPOINT, json=payload, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return None
        blocks = r.json().get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return _extract_json(text)
    except Exception:
        return None


def _extract_json(text):
    """Pull the first JSON object/array out of a text reply (handles code fences
    and leading prose)."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    try:
        return json.loads(t)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    return None
