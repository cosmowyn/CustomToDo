from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta

from query_parsing import parse_quick_add


PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def collect_template_placeholders(payload) -> list[str]:
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
            return
        if isinstance(node, list):
            for v in node:
                walk(v)
            return
        if isinstance(node, str):
            for m in PLACEHOLDER_RE.finditer(node):
                name = str(m.group(1) or "").strip()
                if name:
                    found.add(name)

    walk(payload)
    return sorted(found, key=lambda s: s.lower())


def _replace_in_string(text: str, values: dict[str, str]) -> str:
    def _sub(m):
        key = str(m.group(1) or "")
        return str(values.get(key, ""))

    return PLACEHOLDER_RE.sub(_sub, str(text or ""))


def _normalize_due_value(raw: str | None):
    s = str(raw or "").strip()
    if not s:
        return None

    # ISO date
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        return s[:10]

    # dd-mmm-yyyy
    try:
        return datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except Exception:
        pass

    # natural phrases supported by quick-add parser
    parsed = parse_quick_add(f"x {s}")
    if parsed.due_date:
        return parsed.due_date

    if s.lower() in {"today", "now"}:
        return datetime.now().date().isoformat()
    if s.lower() == "tomorrow":
        return (datetime.now().date() + timedelta(days=1)).isoformat()

    return s


def apply_template_values(payload: dict, values: dict[str, str]) -> dict:
    data = copy.deepcopy(payload or {})

    def walk(node):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                next_v = walk(v)
                if k == "due_date" and isinstance(next_v, str):
                    next_v = _normalize_due_value(next_v)
                out[k] = next_v
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return _replace_in_string(node, values)
        return node

    return walk(data)
