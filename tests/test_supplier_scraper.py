# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests du scraper prudent de références fournisseurs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.supplier_scraper.config import parse_simple_yaml
from tools.supplier_scraper.parser import (
    detect_anti_bot,
    detect_public_price_details,
    extract_links,
    extract_product_option_attributes,
    parse_product_page,
)
from tools.supplier_scraper.import_to_labeco2 import import_observations
from tools.supplier_scraper.storage import LocalCaptureStorage, SupplierStorage
from ui.sqlite_schema import ensure_app_schema


FIXTURES = Path(__file__).parent / "fixtures" / "supplier_scraper"


def test_schema_adds_supplier_scraper_tables():
    conn = sqlite3.connect(":memory:")
    ensure_app_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert "supplier_generic_products" in tables
    assert "supplier_references" in tables
    assert "supplier_price_cache" in tables
    assert "supplier_scrape_runs" in tables
    assert "supplier_fetch_log" in tables


def test_parse_product_page_extracts_minimum_fields():
    html = (FIXTURES / "sample_product.html").read_text(encoding="utf-8")
    candidate = parse_product_page(
        supplier="TEST",
        product_url="https://example.org/store/product/TALC-1000",
        html_text=html,
        retrieval_date="2026-05-26T12:00:00+00:00",
        rules={
            "generic_category": "poudre",
            "ref_patterns": [r"Référence:\s*(?P<ref>[A-Z0-9._-]+)"],
            "packaging_patterns": [r"Conditionnement:\s*(?P<pack>[^\n]+)"],
        },
    )

    assert candidate is not None
    assert candidate.supplier_product_ref == "TALC-1000"
    assert candidate.product_name_short == "Talc pur pour laboratoire, 1 kg"
    assert candidate.packaging_text == "1 kg"
    assert candidate.price_publicly_visible
    assert candidate.currency_detected == "EUR"
    assert candidate.price_text == "24,50 €"
    assert candidate.price_value == 24.5
    assert candidate.source_html_hash


def test_parse_product_page_accepts_html_name_patterns_without_meta():
    html = """
    <html><body>
      <h1>Gants nitrile taille M</h1>
      <p>Reference: NITRILE-M</p>
      <p>Packaging: boite de 100</p>
    </body></html>
    """

    candidate = parse_product_page(
        supplier="TEST",
        product_url="https://example.org/store/product/NITRILE-M",
        html_text=html,
        retrieval_date="2026-05-26T12:00:00+00:00",
        rules={
            "ref_patterns": [r"Reference:\s*(?P<ref>[A-Z0-9._-]+)"],
            "name_patterns": [r"<h1[^>]*>(?P<name>.*?)</h1>"],
            "packaging_patterns": [r"Packaging:\s*(?P<pack>[^\n]+)"],
        },
    )

    assert candidate is not None
    assert candidate.product_name_short == "Gants nitrile taille M"
    assert candidate.packaging_text == "boite de 100"


def test_parse_product_page_accepts_multiline_html_name_patterns():
    html = """
    <html><body>
      <h1 id="qa_item_header_text">
        Fisherbrand&trade;&nbsp;Gants jetables en nitrile Indigo 4.0
        <input type="hidden" value="ignored">
      </h1>
      <span>Code produit <span>17909980</span></span>
    </body></html>
    """

    candidate = parse_product_page(
        supplier="Fisher Scientific",
        product_url="https://www.fishersci.fr/shop/products/indigo-nitrile-disposable-gloves-5/17909980",
        html_text=html,
        retrieval_date="2026-05-27T12:00:00+00:00",
        rules={
            "name_patterns": [r"<h1[^>]*>(?P<name>.*?)</h1>"],
            "url_ref_patterns": [r"/shop/products/[^/]+/(?P<ref>[0-9A-Z]+)"],
        },
    )

    assert candidate is not None
    assert candidate.supplier_product_ref == "17909980"
    assert candidate.product_name_short == "Fisherbrand™ Gants jetables en nitrile Indigo 4.0"


def test_parse_product_page_can_use_url_as_reference_fallback():
    candidate = parse_product_page(
        supplier="VWR",
        product_url="https://www.vwr.com/fr/en/product/9695384/vwr-nitrilelight-nitrile-gloves",
        html_text="<html><body><h1>VWR NitrileLight Nitrile Gloves</h1></body></html>",
        retrieval_date="2026-05-26T12:00:00+00:00",
        rules={
            "name_patterns": [r"<h1[^>]*>(?P<name>.*?)</h1>"],
            "ref_patterns": [r"Reference:\s*(?P<ref>[A-Z0-9._-]+)"],
            "url_ref_patterns": [r"/product/(?P<ref>[0-9]+)/"],
        },
    )

    assert candidate is not None
    assert candidate.supplier_product_ref == "9695384"
    assert candidate.product_name_short == "VWR NitrileLight Nitrile Gloves"


def test_parse_product_page_extracts_variant_refs():
    html = """
    <html><body>
      <h1>Gants nitrile</h1>
      <script>
        _productServiceResponse.siblings = ["17909980","17999970","17929980"];
      </script>
    </body></html>
    """

    candidate = parse_product_page(
        supplier="Fisher Scientific",
        product_url="https://www.fishersci.fr/shop/products/gloves/17909980",
        html_text=html,
        retrieval_date="2026-05-27T12:00:00+00:00",
        rules={
            "name_patterns": [r"<h1[^>]*>(?P<name>.*?)</h1>"],
            "url_ref_patterns": [r"/shop/products/[^/]+/(?P<ref>[0-9A-Z]+)"],
            "variant_ref_patterns": [r"_productServiceResponse\.siblings\s*=\s*\[(?P<refs>[^\]]+)\]"],
        },
    )

    assert candidate is not None
    assert candidate.variant_refs == ("17909980", "17999970", "17929980")


def test_parse_product_page_extracts_fisher_variant_attributes_and_packaging():
    html = """
    <html><body>
      <h1>Gants nitrile</h1>
      <table>
        <thead>
          <tr><th>Code produit</th><th>Dimensions</th><th>unitSize</th></tr>
        </thead>
        <tbody>
          <tr class="product_options_table_row" data-partnumber="17919980">
            <td>17919980</td>
            <td data-selector="XL">XL</td>
            <td data-selector="200pices">200 pièces</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """

    candidate = parse_product_page(
        supplier="Fisher Scientific",
        product_url="https://www.fishersci.fr/shop/products/gloves/17919980",
        html_text=html,
        retrieval_date="2026-05-27T12:00:00+00:00",
        rules={
            "name_patterns": [r"<h1[^>]*>(?P<name>.*?)</h1>"],
            "url_ref_patterns": [r"/shop/products/[^/]+/(?P<ref>[0-9A-Z]+)"],
        },
    )

    assert candidate is not None
    assert candidate.variant_attributes == (("Dimensions", "XL"), ("unitSize", "200 pièces"))
    assert candidate.packaging_text == "200 pièces"


def test_extract_product_option_attributes_handles_missing_row():
    assert extract_product_option_attributes("<html></html>", "17919980") == ()


def test_extract_links_normalizes_relative_urls():
    html = (FIXTURES / "sample_product.html").read_text(encoding="utf-8")

    links = extract_links(html, "https://example.org/category")

    assert "https://example.org/store/product/TALC-1000" in links


def test_detect_public_price_details_ignores_packaging_near_currency_word():
    visible, currency, price_text, price_value = detect_public_price_details("unitSize 170 pièces eur")

    assert not visible
    assert currency == ""
    assert price_text == ""
    assert price_value is None


def test_detect_public_price_details_ignores_internal_codes_near_currency_word():
    visible, currency, price_text, price_value = detect_public_price_details("unitPK eur 90626")

    assert not visible
    assert currency == ""
    assert price_text == ""
    assert price_value is None


def test_detect_anti_bot_handles_cloudflare_turnstile_shell():
    html = """
    <html><body>
      <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
      <app-root></app-root>
    </body></html>
    """

    assert detect_anti_bot(html)


def test_storage_upsert_is_idempotent(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    storage = SupplierStorage(db_path)
    html = (FIXTURES / "sample_product.html").read_text(encoding="utf-8")
    candidate = parse_product_page(
        supplier="TEST",
        product_url="https://example.org/store/product/TALC-1000",
        html_text=html,
        retrieval_date="2026-05-26T12:00:00+00:00",
        rules={
            "generic_category": "poudre",
            "ref_patterns": [r"Référence:\s*(?P<ref>[A-Z0-9._-]+)"],
            "packaging_patterns": [r"Conditionnement:\s*(?P<pack>[^\n]+)"],
        },
    )
    assert candidate is not None

    with storage.connect() as conn:
        first = storage.upsert_reference(conn, candidate)
        second = storage.upsert_reference(conn, candidate)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM supplier_references").fetchone()[0]
        generic_count = conn.execute("SELECT COUNT(*) FROM supplier_generic_products").fetchone()[0]

    assert first.inserted
    assert second.updated
    assert count == 1
    assert generic_count == 1


def test_local_capture_storage_records_price_snapshot(tmp_path):
    db_path = tmp_path / "private_capture.sqlite"
    storage = LocalCaptureStorage(db_path)
    html = (FIXTURES / "sample_product.html").read_text(encoding="utf-8")
    candidate = parse_product_page(
        supplier="TEST",
        product_url="https://example.org/store/product/TALC-1000",
        html_text=html,
        retrieval_date="2026-05-26T12:00:00+00:00",
        rules={
            "generic_category": "poudre",
            "ref_patterns": [r"Référence:\s*(?P<ref>[A-Z0-9._-]+)"],
            "packaging_patterns": [r"Conditionnement:\s*(?P<pack>[^\n]+)"],
        },
    )
    assert candidate is not None

    with storage.connect() as conn:
        storage.capture_candidate(conn, candidate, source_html_cache_path="/tmp/page.html")
        conn.commit()
        observations = conn.execute("SELECT COUNT(*) FROM supplier_scrape_observations").fetchone()[0]
        observation = conn.execute(
            "SELECT packaging_text, variant_attributes_json FROM supplier_scrape_observations"
        ).fetchone()
        prices = conn.execute(
            "SELECT price_text, price_value, currency FROM supplier_local_price_snapshots"
        ).fetchone()

    assert observations == 1
    assert observation["packaging_text"] == "1 kg"
    assert observation["variant_attributes_json"] == "{}"
    assert prices["price_text"] == "24,50 €"
    assert prices["price_value"] == 24.5
    assert prices["currency"] == "EUR"


def test_import_private_scrape_to_labeco2_is_idempotent(tmp_path):
    source_db = tmp_path / "private_capture.sqlite"
    source_storage = LocalCaptureStorage(source_db)
    html = (FIXTURES / "sample_product.html").read_text(encoding="utf-8")
    candidate = parse_product_page(
        supplier="TEST",
        product_url="https://example.org/store/product/TALC-1000",
        html_text=html,
        retrieval_date="2026-05-26T12:00:00+00:00",
        rules={
            "generic_category": "poudre",
            "ref_patterns": [r"Référence:\s*(?P<ref>[A-Z0-9._-]+)"],
            "packaging_patterns": [r"Conditionnement:\s*(?P<pack>[^\n]+)"],
        },
    )
    assert candidate is not None

    with source_storage.connect() as source_conn:
        source_storage.capture_candidate(source_conn, candidate)
        source_conn.commit()

    target_conn = sqlite3.connect(":memory:")
    target_conn.execute(
        """
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            brand TEXT,
            reference TEXT,
            code_nacres TEXT,
            product_type TEXT NOT NULL,
            sold_packaging_label TEXT,
            units_per_sold_packaging INTEGER,
            price_sold_packaging REAL,
            sold_unit_volume_ml REAL,
            supplier_catalogue_id TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT,
            updated_at TEXT,
            note TEXT
        )
        """
    )
    with source_storage.connect() as source_conn:
        first = import_observations(source_conn, target_conn, supplier="TEST")
        target_conn.commit()
        second = import_observations(source_conn, target_conn, supplier="TEST")
        target_conn.commit()

    assert first.supplier_references_inserted == 1
    assert first.supplier_catalogue_inserted == 1
    assert first.price_snapshots_inserted == 1
    assert first.commercial_products_created_pending == 1
    assert second.supplier_references_updated == 1
    assert second.supplier_catalogue_updated == 1
    assert second.price_snapshots_inserted == 0
    assert second.commercial_products_existing == 1
    assert second.commercial_products_pending_updated == 0

    product = target_conn.execute(
        """
        SELECT name, reference, product_type, sold_packaging_label,
               units_per_sold_packaging, price_sold_packaging, status
        FROM commercial_products
        """
    ).fetchone()
    assert tuple(product) == (
        "Talc pur pour laboratoire, 1 kg",
        "TALC-1000",
        "solid",
        "1 kg",
        1,
        24.5,
        "pending",
    )


def test_simple_yaml_parser_handles_supplier_config():
    data = parse_simple_yaml(
        """
        dry_run: true
        limits:
          max_pages_per_run: 3
        suppliers:
          - name: "TEST"
            enabled: true
            start_urls: ["https://example.org/search"]
            product_url_patterns:
              - "/product/"
        """
    )

    assert data["dry_run"] is True
    assert data["limits"]["max_pages_per_run"] == 3
    assert data["suppliers"][0]["name"] == "TEST"
    assert data["suppliers"][0]["product_url_patterns"] == ["/product/"]


def test_simple_yaml_parser_keeps_quoted_regex_with_colon_as_string():
    data = parse_simple_yaml(
        r'''
        ref_patterns:
          - "(?:Référence|Reference)\s*[:#-]?\s*(?P<ref>[A-Z0-9._-]{4,})"
        '''
    )

    assert data["ref_patterns"] == [
        r"(?:Référence|Reference)\s*[:#-]?\s*(?P<ref>[A-Z0-9._-]{4,})"
    ]
