# SPDX-License-Identifier: GPL-3.0-or-later
"""Extraction prudente des données produits depuis HTML fournisseur."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin


_PRICE_AMOUNT_RE = r"\d+(?:[\s.]\d{3})*[,.]\d{1,2}"
_DEFAULT_PRICE_RE = re.compile(
    rf"(?:(?P<currency1>€|EUR|USD|\$|GBP|£)\s*(?P<amount1>{_PRICE_AMOUNT_RE})|"
    rf"(?P<amount2>{_PRICE_AMOUNT_RE})\s*(?P<currency2>€|EUR|USD|\$|GBP|£))",
    re.IGNORECASE,
)
_ANTI_BOT_RE = re.compile(
    r"captcha|robot check|access denied|unusual traffic|temporarily blocked|verify you are human|"
    r"challenges\.cloudflare\.com|turnstile|cf-chl|checking your browser",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProductCandidate:
    supplier: str
    supplier_product_ref: str
    product_url: str
    product_name_short: str
    generic_category: str
    packaging_text: str
    price_publicly_visible: bool
    currency_detected: str
    retrieval_date: str
    source_html_hash: str
    scraping_notes: str = ""
    price_text: str = ""
    price_value: float | None = None
    variant_refs: tuple[str, ...] = ()
    variant_attributes: tuple[tuple[str, str], ...] = ()


class ExtractedHTML(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []
        self.meta: dict[str, str] = {}
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(urljoin(self.base_url, attrs_dict["href"]))
        if tag == "meta":
            key = attrs_dict.get("property") or attrs_dict.get("name")
            content = attrs_dict.get("content")
            if key and content:
                self.meta[key.lower()] = html.unescape(content).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            text = " ".join(html.unescape(data).split())
            if text:
                self.text_parts.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts)


def html_hash(html_text: str) -> str:
    return hashlib.sha256(html_text.encode("utf-8", errors="replace")).hexdigest()


def extract_html(html_text: str, base_url: str) -> ExtractedHTML:
    parser = ExtractedHTML(base_url)
    parser.feed(html_text)
    return parser


def detect_anti_bot(html_text: str) -> bool:
    return bool(_ANTI_BOT_RE.search(html_text[:20000]))


def _clean_extracted(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def _first_regex(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if not match:
            continue
        if match.groupdict():
            for value in match.groupdict().values():
                if value:
                    return _clean_extracted(value)
        if match.groups():
            return _clean_extracted(match.group(1))
        return _clean_extracted(match.group(0))
    return ""


def _currency_from_match(match: re.Match[str]) -> str:
    currency = (match.groupdict().get("currency1") or match.groupdict().get("currency2") or "").upper()
    return {
        "€": "EUR",
        "$": "USD",
        "£": "GBP",
    }.get(currency, currency)


def _price_value_from_match(match: re.Match[str]) -> float | None:
    amount = match.groupdict().get("amount1") or match.groupdict().get("amount2") or ""
    amount = amount.replace("\u00a0", " ").replace(" ", "").strip()
    if "," in amount and "." in amount:
        amount = amount.replace(".", "").replace(",", ".")
    elif "," in amount:
        amount = amount.replace(",", ".")
    try:
        return float(amount)
    except ValueError:
        return None


def detect_public_price_details(text: str) -> tuple[bool, str, str, float | None]:
    match = _DEFAULT_PRICE_RE.search(text)
    if not match:
        return False, "", "", None
    return True, _currency_from_match(match), _clean_extracted(match.group(0)), _price_value_from_match(match)


def detect_public_price(text: str) -> tuple[bool, str]:
    visible, currency, _price_text, _price_value = detect_public_price_details(text)
    return visible, currency


def extract_variant_refs(patterns: list[str], text: str) -> tuple[str, ...]:
    refs: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL):
            if match.groupdict():
                chunk = match.groupdict().get("refs") or next(
                    (value for value in match.groupdict().values() if value),
                    "",
                )
            elif match.groups():
                chunk = match.group(1)
            else:
                chunk = match.group(0)
            for ref in re.findall(r"\b[A-Z0-9][A-Z0-9._-]{3,}\b", chunk, re.IGNORECASE):
                clean_ref = ref.strip()
                if clean_ref and clean_ref not in refs:
                    refs.append(clean_ref)
    return tuple(refs)


def extract_product_option_attributes(html_text: str, supplier_ref: str) -> tuple[tuple[str, str], ...]:
    row_match = re.search(
        rf"<tr\b(?=[^>]*data-partnumber=[\"']{re.escape(supplier_ref)}[\"'])[^>]*>(?P<row>.*?)</tr>",
        html_text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if not row_match:
        return ()

    table_start = html_text.rfind("<table", 0, row_match.start())
    table_end = html_text.find("</table>", row_match.end())
    table_html = html_text[table_start : table_end + len("</table>")] if table_start >= 0 and table_end >= 0 else ""
    headers = [
        _clean_extracted(match.group(1))
        for match in re.finditer(r"<th\b[^>]*>(.*?)</th>", table_html, re.IGNORECASE | re.DOTALL)
    ]
    cells = [
        _clean_extracted(match.group(1))
        for match in re.finditer(r"<td\b[^>]*>(.*?)</td>", row_match.group("row"), re.IGNORECASE | re.DOTALL)
    ]

    attributes: list[tuple[str, str]] = []
    for index, value in enumerate(cells):
        if not value or value == supplier_ref:
            continue
        label = headers[index] if index < len(headers) and headers[index] else f"option_{index}"
        if (label, value) not in attributes:
            attributes.append((label, value))
    return tuple(attributes)


def _attribute_value(attributes: tuple[tuple[str, str], ...], keys: set[str]) -> str:
    normalized = {key.casefold() for key in keys}
    for key, value in attributes:
        if key.casefold() in normalized:
            return value
    return ""


def extract_links(html_text: str, page_url: str) -> list[str]:
    parsed = extract_html(html_text, page_url)
    return parsed.links


def parse_product_page(
    *,
    supplier: str,
    product_url: str,
    html_text: str,
    retrieval_date: str,
    rules: dict[str, Any],
) -> ProductCandidate | None:
    parsed = extract_html(html_text, product_url)
    text = parsed.text
    name_patterns = rules.get("name_patterns") or []
    ref_patterns = rules.get("ref_patterns") or []
    url_ref_patterns = rules.get("url_ref_patterns") or []
    packaging_patterns = rules.get("packaging_patterns") or []
    variant_ref_patterns = rules.get("variant_ref_patterns") or []

    text_lines = text.splitlines()
    product_name = (
        _first_regex(name_patterns, text)
        or _first_regex(name_patterns, html_text)
        or parsed.meta.get("og:title", "")
        or parsed.meta.get("twitter:title", "")
        or (text_lines[0] if text_lines else "")
    )
    supplier_ref = _first_regex(url_ref_patterns, product_url)
    if not supplier_ref:
        supplier_ref = _first_regex(ref_patterns, text)
    packaging = _first_regex(packaging_patterns, text)
    price_visible, currency, price_text, price_value = detect_public_price_details(text)
    variant_refs = extract_variant_refs(variant_ref_patterns, html_text)
    variant_attributes = extract_product_option_attributes(html_text, supplier_ref) if supplier_ref else ()
    if not packaging:
        packaging = _attribute_value(
            variant_attributes,
            {"unitSize", "Conditionnement", "Packaging", "Pack size", "Taille du pack"},
        )
    notes: list[str] = []
    if not supplier_ref:
        notes.append("référence fournisseur non détectée")
    if detect_anti_bot(html_text):
        notes.append("signal anti-bot détecté dans le HTML")
    if not product_name:
        notes.append("nom court non détecté")

    if not supplier_ref:
        return None

    return ProductCandidate(
        supplier=supplier,
        supplier_product_ref=supplier_ref,
        product_url=product_url,
        product_name_short=product_name[:500],
        generic_category=str(rules.get("generic_category") or ""),
        packaging_text=packaging[:500],
        price_publicly_visible=price_visible,
        currency_detected=currency,
        retrieval_date=retrieval_date,
        source_html_hash=html_hash(html_text),
        scraping_notes="; ".join(notes),
        price_text=price_text,
        price_value=price_value,
        variant_refs=variant_refs,
        variant_attributes=variant_attributes,
    )
