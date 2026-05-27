# SPDX-License-Identifier: GPL-3.0-or-later
"""Crawler lent, cache et respectueux pour références fournisseurs."""

from __future__ import annotations

import hashlib
import logging
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.supplier_scraper.parser import (
    ProductCandidate,
    detect_anti_bot,
    extract_links,
    html_hash,
    parse_product_page,
)
from tools.supplier_scraper.storage import LocalCaptureStorage, SupplierStorage


logger = logging.getLogger(__name__)


class StopScraping(RuntimeError):
    """Erreur volontaire : le site demande implicitement ou explicitement d'arrêter."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    html_text: str
    status_code: int
    from_cache: bool
    html_hash: str


@dataclass
class CrawlStats:
    fetched_pages: int = 0
    product_pages: int = 0
    stored_references: int = 0
    skipped_without_ref: int = 0
    stopped_reason: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _same_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in allowed_domains)


def _matches_any(url: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)


class PoliteHttpClient:
    def __init__(self, config: dict[str, Any], supplier: dict[str, Any]):
        request_cfg = config.get("request", {})
        self.user_agent = request_cfg.get(
            "user_agent",
            "LABeCO2 research carbon-footprint tool - contact: labeco2.contact@gmail.com",
        )
        self.min_delay = max(10.0, float(request_cfg.get("min_delay_seconds", 10)))
        self.max_delay = max(self.min_delay, float(request_cfg.get("max_delay_seconds", 30)))
        self.timeout = float(request_cfg.get("timeout_seconds", 30))
        self.respect_robots = bool(request_cfg.get("respect_robots_txt", True))
        self.use_cache = bool(request_cfg.get("use_cache", True))
        self.stop_status_codes = set(request_cfg.get("stop_status_codes", [403, 429]))
        cache_root = Path(request_cfg.get("cache_dir", ".cache/labeco2_supplier_scraper"))
        self.cache_dir = cache_root / str(supplier["name"]).lower().replace(" ", "_")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_at = 0.0

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{_url_hash(url)}.html"

    def cache_path_for(self, url: str) -> Path:
        return self._cache_path(url)

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base in self.robots:
            return self.robots[base]
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(urllib.parse.urljoin(base, "/robots.txt"))
        try:
            parser.read()
        except Exception as exc:
            logger.warning("robots.txt illisible pour %s: %s", base, exc)
        self.robots[base] = parser
        return parser

    def _wait(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        elapsed = time.monotonic() - self._last_request_at
        remaining = delay - elapsed
        if remaining > 0:
            logger.info("Pause polie %.1fs avant prochaine requête", remaining)
            time.sleep(remaining)

    def fetch(self, url: str) -> FetchResult:
        cache_path = self._cache_path(url)
        if self.use_cache and cache_path.exists():
            html_text = cache_path.read_text(encoding="utf-8", errors="replace")
            if detect_anti_bot(html_text):
                raise StopScraping(f"Signal anti-bot détecté dans le cache pour {url}")
            return FetchResult(url, html_text, 200, True, html_hash(html_text))

        if self.respect_robots and not self._robots_for(url).can_fetch(self.user_agent, url):
            raise StopScraping(f"robots.txt interdit l'accès à {url}")

        self._wait()
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status_code = int(response.status)
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                html_text = raw.decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in self.stop_status_codes:
                raise StopScraping(f"HTTP {exc.code} reçu sur {url}") from exc
            raise

        self._last_request_at = time.monotonic()
        if status_code in self.stop_status_codes:
            raise StopScraping(f"HTTP {status_code} reçu sur {url}")
        if detect_anti_bot(html_text):
            raise StopScraping(f"Signal anti-bot détecté sur {url}")

        if self.use_cache:
            cache_path.write_text(html_text, encoding="utf-8")
        return FetchResult(url, html_text, status_code, False, html_hash(html_text))


class SupplierCrawler:
    def __init__(self, config: dict[str, Any], supplier: dict[str, Any], storage: SupplierStorage):
        self.config = config
        self.supplier = supplier
        self.storage = storage
        self.client = PoliteHttpClient(config, supplier)
        limits = config.get("limits", {})
        self.max_pages = int(limits.get("max_pages_per_run", 30))
        self.max_products = int(limits.get("max_products_per_run", 100))
        self.allowed_domains = supplier.get("allowed_domains") or [
            urllib.parse.urlparse(supplier.get("base_url", "")).netloc
        ]
        self.crawl_patterns = supplier.get("crawl_url_patterns") or []
        self.product_patterns = supplier.get("product_url_patterns") or []
        self.deny_patterns = supplier.get("deny_url_patterns") or []
        local_cfg = config.get("local_capture") or {}
        self.local_capture = (
            LocalCaptureStorage(local_cfg.get("database_path", "private/supplier_scraping_lab.sqlite"))
            if local_cfg.get("enabled", False)
            else None
        )
        self.capture_during_dry_run = bool(local_cfg.get("capture_during_dry_run", False))
        self.expand_variant_refs = bool(supplier.get("expand_variant_refs", True))

    def _allowed(self, url: str) -> bool:
        if not _same_allowed_domain(url, self.allowed_domains):
            return False
        if self.deny_patterns and _matches_any(url, self.deny_patterns):
            return False
        return True

    def _is_product_url(self, url: str) -> bool:
        return bool(self.product_patterns and _matches_any(url, self.product_patterns))

    def _is_crawl_url(self, url: str) -> bool:
        return bool(self.crawl_patterns and _matches_any(url, self.crawl_patterns))

    def _variant_url(self, product_url: str, variant_ref: str) -> str:
        clean_url = urllib.parse.urldefrag(product_url)[0]
        parsed = urllib.parse.urlparse(clean_url)
        path = parsed.path.rstrip("/")
        if not path:
            return ""
        parts = path.split("/")
        parts[-1] = urllib.parse.quote(variant_ref, safe="")
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/".join(parts), "", "", ""))

    def _queue_variant_urls(
        self,
        product_url: str,
        candidate: ProductCandidate,
        queue: list[str],
        seen_urls: set[str],
        seen_product_urls: set[str],
    ) -> None:
        if not self.expand_variant_refs:
            return
        for variant_ref in candidate.variant_refs:
            if variant_ref == candidate.supplier_product_ref:
                continue
            variant_url = self._variant_url(product_url, variant_ref)
            if not variant_url or variant_url in seen_urls or variant_url in seen_product_urls:
                continue
            if self._allowed(variant_url) and self._is_product_url(variant_url):
                queue.append(variant_url)
                seen_product_urls.add(variant_url)

    def run(self, *, dry_run: bool, config_path: str = "") -> CrawlStats:
        stats = CrawlStats()
        start_urls = list(
            dict.fromkeys(urllib.parse.urldefrag(url)[0] for url in self.supplier.get("start_urls") or [])
        )
        with self.storage.connect() as conn:
            run_id = self.storage.start_run(
                conn,
                supplier=self.supplier["name"],
                dry_run=dry_run,
                config_path=config_path,
                start_url_count=len(start_urls),
            )
            queue = list(start_urls)
            seen_urls: set[str] = set()
            seen_product_urls: set[str] = set()
            seen_supplier_refs: set[str] = set()
            try:
                while queue and stats.fetched_pages < self.max_pages and stats.product_pages < self.max_products:
                    url = queue.pop(0)
                    if url in seen_urls or not self._allowed(url):
                        continue
                    seen_urls.add(url)
                    logger.info("Fetch %s", url)
                    result = self.client.fetch(url)
                    stats.fetched_pages += 1
                    self.storage.log_fetch(
                        conn,
                        run_id=run_id,
                        supplier=self.supplier["name"],
                        url=url,
                        status_code=result.status_code,
                        from_cache=result.from_cache,
                        html_hash=result.html_hash,
                    )

                    if self._is_product_url(url):
                        seen_product_urls.add(url)
                        candidate = parse_product_page(
                            supplier=self.supplier["name"],
                            product_url=url,
                            html_text=result.html_text,
                            retrieval_date=_now_iso(),
                            rules=self.supplier,
                        )
                        stats.product_pages += 1
                        if candidate is None:
                            stats.skipped_without_ref += 1
                            continue
                        if candidate.supplier_product_ref in seen_supplier_refs:
                            continue
                        seen_supplier_refs.add(candidate.supplier_product_ref)
                        self._store_candidate(conn, candidate, dry_run, stats)
                        self._queue_variant_urls(url, candidate, queue, seen_urls, seen_product_urls)
                        continue

                    for link in extract_links(result.html_text, url):
                        clean_url = urllib.parse.urldefrag(link)[0]
                        if clean_url in seen_urls or not self._allowed(clean_url):
                            continue
                        if self._is_product_url(clean_url):
                            if clean_url not in seen_product_urls:
                                queue.append(clean_url)
                        elif self._is_crawl_url(clean_url):
                            queue.append(clean_url)

                final_status = "stopped_by_limit" if queue else "completed"
            except StopScraping as exc:
                stats.stopped_reason = str(exc)
                logger.warning("Arrêt volontaire du scraping: %s", exc)
                final_status = "stopped"
            except Exception as exc:
                stats.stopped_reason = str(exc)
                logger.exception("Erreur de scraping")
                final_status = "error"
            self.storage.finish_run(
                conn,
                run_id,
                status=final_status,
                request_count=stats.fetched_pages,
                stored_reference_count=stats.stored_references,
                notes=stats.stopped_reason,
            )
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
        return stats

    def _store_candidate(
        self,
        conn,
        candidate: ProductCandidate,
        dry_run: bool,
        stats: CrawlStats,
    ) -> None:
        logger.info(
            "%s référence %s %s",
            "[dry-run]" if dry_run else "Stockage LABeCO2",
            candidate.supplier,
            candidate.supplier_product_ref,
        )
        if not dry_run:
            self.storage.upsert_reference(conn, candidate)
        if self.local_capture and (not dry_run or self.capture_during_dry_run):
            with self.local_capture.connect() as local_conn:
                self.local_capture.capture_candidate(
                    local_conn,
                    candidate,
                    source_html_cache_path=str(self.client.cache_path_for(candidate.product_url)),
                )
                local_conn.commit()
        stats.stored_references += 1
