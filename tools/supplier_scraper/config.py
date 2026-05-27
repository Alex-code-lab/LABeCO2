# SPDX-License-Identifier: GPL-3.0-or-later
"""Chargement de configuration pour le scraper fournisseur LABeCO2."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any

_LIST_MAPPING_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:")


def _strip_comment(line: str) -> str:
    in_quote = False
    quote = ""
    result = []
    for char in line:
        if char in {"'", '"'}:
            if not in_quote:
                in_quote = True
                quote = char
            elif quote == char:
                in_quote = False
        if char == "#" and not in_quote:
            break
        result.append(char)
    return "".join(result).rstrip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _next_significant(lines: list[str], start: int) -> str:
    for line in lines[start:]:
        clean = _strip_comment(line)
        if clean.strip():
            return clean
    return ""


def _parse_block(lines: list[str], start: int, indent: int) -> tuple[Any, int]:
    next_line = _next_significant(lines, start)
    container: Any = [] if next_line.lstrip().startswith("- ") else {}

    i = start
    while i < len(lines):
        raw = _strip_comment(lines[i])
        if not raw.strip():
            i += 1
            continue
        current_indent = len(raw) - len(raw.lstrip(" "))
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"Indentation YAML inattendue ligne {i + 1}: {lines[i]!r}")
        text = raw.strip()

        if isinstance(container, list):
            if not text.startswith("- "):
                break
            item_text = text[2:].strip()
            if not item_text:
                item, i = _parse_block(lines, i + 1, indent + 2)
                container.append(item)
                continue
            if _LIST_MAPPING_RE.match(item_text):
                key, value = item_text.split(":", 1)
                item = {key.strip(): _parse_scalar(value)}
                i += 1
                while i < len(lines):
                    child = _strip_comment(lines[i])
                    if not child.strip():
                        i += 1
                        continue
                    child_indent = len(child) - len(child.lstrip(" "))
                    if child_indent <= indent:
                        break
                    child_text = child.strip()
                    if ":" not in child_text:
                        raise ValueError(f"Ligne YAML non supportée {i + 1}: {lines[i]!r}")
                    child_key, child_value = child_text.split(":", 1)
                    child_key = child_key.strip()
                    child_value = child_value.strip()
                    if child_value:
                        item[child_key] = _parse_scalar(child_value)
                        i += 1
                    else:
                        item[child_key], i = _parse_block(lines, i + 1, child_indent + 2)
                container.append(item)
                continue
            container.append(_parse_scalar(item_text))
            i += 1
            continue

        if ":" not in text:
            raise ValueError(f"Ligne YAML non supportée {i + 1}: {lines[i]!r}")
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            container[key] = _parse_scalar(value)
            i += 1
        else:
            container[key], i = _parse_block(lines, i + 1, indent + 2)
    return container, i


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse un sous-ensemble YAML suffisant pour config.yaml.

    PyYAML n'est pas une dépendance actuelle du projet. Cette fonction couvre les
    dictionnaires, listes, booléens, nombres et chaînes utilisés par la config.
    """
    lines = textwrap.dedent(text).splitlines()
    data, index = _parse_block(lines, 0, 0)
    if index < len(lines):
        raise ValueError("Fin de fichier YAML inattendue.")
    if not isinstance(data, dict):
        raise ValueError("La configuration doit être un dictionnaire YAML.")
    return data


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded or {}
    except ModuleNotFoundError:
        pass
    stripped = text.lstrip()
    if stripped.startswith("{"):
        return json.loads(text)
    return parse_simple_yaml(text)


def enabled_suppliers(config: dict[str, Any]) -> list[dict[str, Any]]:
    suppliers = config.get("suppliers") or []
    if isinstance(suppliers, dict):
        suppliers = [dict(value, name=key) for key, value in suppliers.items()]
    return [supplier for supplier in suppliers if supplier.get("enabled", False)]
