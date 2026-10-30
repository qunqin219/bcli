"""Output helpers: minimal YAML dumper (no deps) and field selection."""

from __future__ import annotations

from typing import Any


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in ":#{}[]&*!|>'\"%@`\n") or text.strip() != text:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return text


def to_yaml(value: Any, indent: int = 0) -> str:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        if not value:
            return f"{pad}{{}}\n"
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}{key}:")
                lines.append(to_yaml(item, indent + 1).rstrip("\n"))
            else:
                lines.append(f"{pad}{key}: {_scalar(item) if not isinstance(item, (dict, list)) else ('{}' if isinstance(item, dict) else '[]')}")
    elif isinstance(value, list):
        if not value:
            return f"{pad}[]\n"
        for item in value:
            if isinstance(item, dict) and item:
                body = to_yaml(item, indent + 1).rstrip("\n").split("\n")
                first = body[0].lstrip()
                lines.append(f"{pad}- {first}")
                lines.extend(body[1:])
            elif isinstance(item, list) and item:
                lines.append(f"{pad}-")
                lines.append(to_yaml(item, indent + 1).rstrip("\n"))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    else:
        lines.append(f"{pad}{_scalar(value)}")
    return "\n".join(lines) + "\n"


def pick(value: Any, fields: list[str]) -> Any:
    """Keep only the requested keys, recursively for lists of dicts."""
    if not fields:
        return value
    if isinstance(value, list):
        return [pick(item, fields) for item in value]
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if k in fields}
    return value
