"""Shared helpers used across all blueprints."""
import os
import re
import json
import base64
from datetime import datetime, timedelta, date
from flask import request
from dotenv import load_dotenv
from anthropic import Anthropic
import db


# ── FO76 day boundary (noon reset) ──────────────────────────────────────────

def fo76_today():
    """Return the current FO76 'day' as a date string (YYYY-MM-DD).

    FO76 dailies reset at noon, so before 12:00 we're still on yesterday's day.
    """
    now = datetime.now()
    if now.hour < 12:
        return str((now - timedelta(days=1)).date())
    return str(now.date())


def fo76_this_monday():
    """Return the Monday of the current FO76 week (accounting for noon reset)."""
    now = datetime.now()
    effective = now - timedelta(days=1) if now.hour < 12 else now
    monday = effective.date() - timedelta(days=effective.weekday())
    return str(monday)

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# ── Form helpers ──────────────────────────────────────────────────────────────

def fi(key, default=0):
    """Get form int value."""
    try:
        return int(request.form.get(key, default))
    except (ValueError, TypeError):
        return default

def ff(key, default=0.0):
    """Get form float value."""
    try:
        return float(request.form.get(key, default))
    except (ValueError, TypeError):
        return default

def fs(key, default=''):
    """Get form string value."""
    return request.form.get(key, default).strip()


# ── Character helper ──────────────────────────────────────────────────────────

def get_active_char_id():
    """Return the active character id (int), defaulting to 1."""
    try:
        return int(db.get_setting('active_character_id') or 1)
    except (ValueError, TypeError):
        return 1


# ── Inventory mirror helpers ──────────────────────────────────────────────────

def _inv_sync(source_table, source_id, name, category, sub_type, qty, weight, value, status, cid=None):
    """Create or update the inventory mirror entry for a section record."""
    if cid is None:
        cid = get_active_char_id()
    existing = db.get_one(
        "SELECT id FROM inventory WHERE source_table=? AND source_id=?",
        (source_table, source_id)
    )
    if existing:
        db.execute(
            "UPDATE inventory SET name=?,category=?,sub_type=?,qty=?,weight_each=?,value_each=?,status=?,character_id=? WHERE id=?",
            (name, category, sub_type, qty, weight, value, status, cid, existing['id'])
        )
    else:
        db.execute(
            "INSERT INTO inventory (name,category,sub_type,qty,weight_each,value_each,status,source_table,source_id,character_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, category, sub_type, qty, weight, value, status, source_table, source_id, cid)
        )

def _inv_delete(source_table, source_id):
    """Remove the inventory mirror for a deleted section record."""
    db.execute(
        "DELETE FROM inventory WHERE source_table=? AND source_id=?",
        (source_table, source_id)
    )


# ── AI helpers ────────────────────────────────────────────────────────────────

_anthropic_client = None

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    return _anthropic_client

_SCAN_PROMPT = """You are reading a Fallout 76 vendor shop screenshot.
Extract every item listed for sale. Return ONLY valid JSON — no markdown, no explanation.

Format:
{
  "vendor_name": "<vendor username shown at top, or empty string>",
  "items": [
    {"item_name": "<name>", "price": <integer caps>, "category": "<category>", "description": "<desc>"}
  ]
}

Rules:
- item_name: strip quantity like "(25)" or "(Known)" prefix. For standalone legendary mods, prefix with "Mod: ".
- price: integer only, no symbols.
- category: one of Weapon / Armor / Power Armor / Plan / Aid / Ammo / Apparel / Mod / Food/Drink / Misc
- description: legendary star rating as "1-star"/"2-star"/"3-star", or other notable detail, else empty string.
- If no vendor items visible, return {"vendor_name": "", "items": []}.
"""

def _scan_image(image_bytes, media_type, api_key, prompt=None):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2048,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': b64}},
                {'type': 'text', 'text': prompt or _SCAN_PROMPT},
            ]
        }]
    )
    return msg.content[0].text

def _extract_json(text):
    """Robustly pull JSON object from model response."""
    text = text.strip()
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
    return None

def _extract_json_array(text):
    """Pull a JSON array from model response."""
    text = text.strip()
    start = text.find('[')
    end   = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return None


def discord_notify(message, embed=None):
    """Send a notification to Discord webhook. Fails silently."""
    url = db.get_setting('discord_webhook_url', '')
    if not url:
        return
    try:
        import requests
        payload = {}
        if embed:
            payload['embeds'] = [embed]
        else:
            payload['content'] = message
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass
