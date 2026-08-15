"""SearXNG-derived keyword -> Playwright Alibaba scrape -> part price lookup —
Section 6.10.

Revisi rancangan.txt: harga part HARUS dicari dari platform e-commerce
(shopee, tokopedia, alibaba, lazada dll), bukan manual servis resmi vendor,
forum, eBay, dll — sumber-sumber itu tidak punya harga jual konsisten dan
tidak merepresentasikan biaya penggantian part yang sebenarnya bisa dibeli.

Revisi besar (mengganti Firecrawl total): Alibaba's search endpoint duduk di
belakang Akamai Bot Manager, yang fingerprint TLS/JA3 — bukan cuma header HTTP
— jadi request/httpx/cookie-hack SELALU diblokir cepat atau lambat (terbukti
lewat investigasi panjang sebelumnya: Firecrawl kena "unusual traffic" secara
tidak konsisten, direct-requests-with-cookie kena "<punish-component />" JS
challenge begitu cookie expired). Playwright menjalankan Chromium sungguhan,
fingerprint-nya identik browser asli, jadi jauh lebih tahan lama tanpa perlu
maintenance cookie manual. Firecrawl (5 container: api, playwright-service,
redis, rabbitmq, nuq-postgres) dihapus total dari docker-compose — Playwright
jalan langsung di proses backend, tidak butuh service terpisah.

Scope: HANYA Alibaba yang di-scrape sekarang (domain lain — Tokopedia, Shopee,
dll — sengaja tidak diproses, per keputusan eksplisit user saat migrasi ini:
lebih baik cakupan sempit tapi reliable daripada resource Playwright dipakai
untuk banyak situs dengan struktur berbeda-beda)."""
from __future__ import annotations

import logging
import re

import httpx
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import settings

logger = logging.getLogger(__name__)

def searxng_search(query_text: str, num_results: int = 5) -> list[dict]:
    """Search SearXNG for candidate URLs. Returns [{"title", "url", "content"}, ...].

    Dipakai oleh crag_graph.py's web-fallback RAG — part_price_search sendiri
    sudah tidak memanggil ini lagi sejak migrasi ke Playwright (lihat modul
    docstring), yang scrape langsung dari keyword tanpa perlu SearXNG sebagai
    perantara pencarian kandidat URL."""
    try:
        resp = httpx.get(
            f"{settings.SEARXNG_BASE_URL}/search",
            params={"q": query_text, "format": "json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])[:num_results]
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in results
        ]
    except Exception:
        logger.exception("searxng_search failed for query=%r", query_text)
        return []


_ALIBABA_SEARCH_URL = (
    "https://www.alibaba.com/search/page"
    "?spm=a2700.prosearch.the-new-header_fy23_pc_search_bar.keydown__Enter"
    "&SearchScene=proSearch"
    "&SearchText={keyword}"
    "&pro=true&from=pcHomeContent"
)

_ALIBABA_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Diinjeksikan ke halaman untuk mengambil pasangan nama produk + harga: dari
# title-area, naik ke parent sampai ketemu ancestor yang juga mengandung
# price-area. Port langsung dari code/scrapping.py (script Playwright yang
# sudah dites manual terhadap Alibaba sungguhan) — logic-nya dipertahankan
# persis, cuma dijadikan konstanta modul instead of file terpisah.
_ALIBABA_EXTRACT_JS = """
() => {
    function findPriceContainer(titleDiv, maxHops = 6) {
        let node = titleDiv;
        for (let i = 0; i < maxHops; i++) {
            node = node.parentElement;
            if (!node) return null;
            const priceDiv = node.querySelector('[data-role="price-area"]');
            if (priceDiv) return priceDiv;
        }
        return null;
    }

    function findProductUrl(titleDiv, maxHops = 6) {
        // Link ke halaman produk spesifik (/product-detail/...) biasanya ada
        // sebagai <a href> pembungkus gambar/slider kartu produk (bukan di
        // dalam title-area itu sendiri) — naik ke ancestor kartu yang sama
        // dengan findPriceContainer, cari <a href*="/product-detail/"> di sana.
        let node = titleDiv;
        for (let i = 0; i < maxHops; i++) {
            node = node.parentElement;
            if (!node) return null;
            const linkTag = node.querySelector('a[href*="/product-detail/"]');
            if (linkTag) {
                const href = linkTag.getAttribute('href');
                if (href) return href.startsWith('//') ? 'https:' + href : href;
            }
        }
        return null;
    }

    const titleAreas = Array.from(document.querySelectorAll('[data-role="title-area"]'));
    const results = [];

    for (const titleDiv of titleAreas) {
        const h2 = titleDiv.querySelector('h2[class*="searchx-product-e-title"]');
        let name = '';

        if (h2) {
            const spans = Array.from(h2.querySelectorAll('span'));
            for (let i = spans.length - 1; i >= 0; i--) {
                const t = spans[i].innerText.trim();
                if (t) { name = t; break; }
            }
            if (!name) name = h2.innerText.trim();
        } else {
            const aTag = titleDiv.querySelector('a');
            name = (aTag || titleDiv).innerText.trim();
        }

        name = name.replace(/\\s+/g, ' ');
        if (!name) continue;

        const priceDiv = findPriceContainer(titleDiv);
        let price = null;
        if (priceDiv) {
            const priceMain = priceDiv.querySelector('.searchx-product-price-price-main');
            price = priceMain ? priceMain.innerText.trim() : null;
        }

        const productUrl = findProductUrl(titleDiv);

        results.push({ name: name, price: price, url: productUrl });
    }

    return results;
}
"""


def playwright_scrape_alibaba(keyword: str, limit: int = 4, timeout_ms: int = 30000) -> list[dict]:
    """Scrape produk Alibaba (nama + harga) via Chromium sungguhan (Playwright).

    Port dari code/scrapping.py — warm-up ke homepage dulu (dapat cookie sesi,
    lebih mirip perilaku user asli) baru pindah ke halaman search, dengan
    navigator.webdriver disamarkan (sinyal umum deteksi bot). Return list
    kosong (bukan exception) kalau elemen produk tidak muncul dalam timeout —
    caller (_search_and_lookup_prices) memperlakukan ini sama seperti "tidak
    bisa di-scrape", skip total tanpa baris apa pun."""
    keyword_encoded = keyword.strip().replace(" ", "+")
    url = _ALIBABA_SEARCH_URL.format(keyword=keyword_encoded)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=_ALIBABA_USER_AGENT,
                viewport={"width": 1366, "height": 900},
                locale="en-US",
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = context.new_page()

            try:
                page.goto("https://www.alibaba.com/", timeout=timeout_ms, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                page.wait_for_selector('[data-role="title-area"]', timeout=timeout_ms)
                page.wait_for_timeout(1000)
            except PlaywrightTimeoutError:
                logger.warning(
                    "playwright_scrape_alibaba: elemen produk tidak muncul dalam %dms untuk keyword=%r "
                    "(kemungkinan butuh captcha manual atau proteksi bot mendeteksi otomasi)",
                    timeout_ms, keyword,
                )
                browser.close()
                return []

            raw_results = page.evaluate(_ALIBABA_EXTRACT_JS)
            browser.close()
    except Exception:
        logger.exception("playwright_scrape_alibaba failed for keyword=%r", keyword)
        return []

    return raw_results[:limit]


# Harga dianggap masuk akal untuk part CNC industrial kalau dalam rentang ini
# — menyaring kartu produk yang harganya "Login untuk lihat harga" atau
# semacamnya yang lolos parsing tapi jelas bukan angka harga asli.
_MIN_PLAUSIBLE_PRICE_IDR = 10_000
_MAX_PLAUSIBLE_PRICE_IDR = 500_000_000

# Ditemukan via inspeksi HTML langsung (bukan asumsi): kartu produk di halaman
# search www.alibaba.com/search/page (yang di-scrape playwright_scrape_alibaba)
# SUDAH menampilkan harga dalam Rupiah langsung — "Rp18.006.649" — BUKAN USD
# seperti asumsi awal yang salah (yang berasal dari investigasi domain BEDA,
# indonesian.alibaba.com/product-detail/..., yang memang pakai USD). Konvensi
# Indonesia: titik = pemisah ribuan, tidak pernah desimal — jadi "18.006.649"
# harus dibaca sebagai satu angka 18006649, bukan di-split per titik.
_ALIBABA_PRICE_RE = re.compile(r"Rp\s?([\d.]+)", re.IGNORECASE)


def _parse_alibaba_price(raw: str | None) -> tuple[float, float] | None:
    """Parse harga Rupiah dari kartu produk Alibaba (mis. "Rp18.006.649" atau
    rentang varian "Rp1.200-3.500") jadi (price_min, price_max). None kalau
    tidak ada angka valid atau di luar rentang wajar."""
    if not raw:
        return None
    matches = _ALIBABA_PRICE_RE.findall(raw)
    if not matches:
        return None
    values = []
    for m in matches:
        numeric = m.replace(".", "").rstrip(",")
        if not numeric:
            continue
        try:
            values.append(float(numeric))
        except ValueError:
            continue
    if not values:
        return None
    lo, hi = min(values), max(values)
    if not (_MIN_PLAUSIBLE_PRICE_IDR <= lo <= _MAX_PLAUSIBLE_PRICE_IDR):
        return None
    return (lo, hi)


def search_part_price(part_name: str, machine_type: str = "Haas CNC", max_candidates: int = 4) -> list[dict]:
    """Section 6.10: cari harga part via Playwright scrape langsung ke halaman
    search Alibaba (lihat playwright_scrape_alibaba) — TIDAK lagi lewat
    SearXNG->scrape-URL-kandidat seperti versi Firecrawl sebelumnya, karena
    Alibaba's own search page sudah jadi satu-satunya sumber (scope: hanya
    Alibaba, lihat modul docstring).

    Query dicoba dulu spesifik (part_name + machine_type), kalau nol produk
    ditemukan otomatis coba ulang dengan keyword lebih longgar (part_name
    saja) — halaman search Alibaba untuk query yang terlalu spesifik/gado-gado
    sering kosong padahal part-nya sendiri ada kalau dicari lebih generik.

    Kalau scrape gagal total (elemen produk tidak muncul, biasanya karena
    proteksi bot Akamai mendeteksi otomasi meski pakai Chromium sungguhan)
    ATAU kartu produk yang ditemukan tidak punya harga yang bisa diparse,
    kartu itu di-SKIP TOTAL — tidak ada baris "tidak ditemukan" apa pun,
    sesuai instruksi eksplisit user.

    Returns list of {"part_name" (nama produk SPESIFIK dari Alibaba, bukan
    nama part yang dicari), "price_min", "price_max", "currency", "source_url"}
    — bisa kosong kalau scrape gagal total atau tidak ada kartu produk dengan
    harga valid.
    """
    query = f"{part_name} {machine_type}".strip()
    lookups = _scrape_and_parse(query, max_candidates)

    if not lookups and query != part_name:
        logger.info("search_part_price: no products for query=%r, retrying broader keyword=%r", query, part_name)
        lookups = _scrape_and_parse(part_name, max_candidates)

    return lookups


_RELEVANCE_STOPWORDS = {
    "cnc", "machine", "haas", "for", "the", "a", "an", "and", "or", "of", "with", "system",
    "part", "parts", "kit", "tool", "industrial", "machinery",
}


def _relevance_keywords(text: str) -> set[str]:
    """Meaningful (non-stopword, length > 2) lowercase words from a query or
    product title — used by _is_relevant_product to reject listings that
    share nothing but generic CNC/machine boilerplate with the search term
    (e.g. searching "grease filter" must not accept a "Range Hood Grease
    Filter" or "DJI Lens Filter" listing just because both say "filter")."""
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _RELEVANCE_STOPWORDS}


def _is_relevant_product(query: str, product_name: str) -> bool:
    """Cheap relevance guard on top of Alibaba's own (loose) search matching
    — rejects a product card that shares NO meaningful keyword at all with
    the part name being searched (e.g. searching "ballscrew" matching a
    drone camera filter or a Harley air cleaner, which was observed in
    testing). This does NOT catch same-category-but-wrong-product noise for
    generic consumable names (e.g. "grease filter" legitimately overlapping
    with an unrelated Range Hood grease filter) — that class of false
    positive is handled upstream by only pricing the primary/specific part
    (see routes_report.py), not by this keyword check."""
    query_kw = _relevance_keywords(query)
    product_kw = _relevance_keywords(product_name)
    if not query_kw or not product_kw:
        return True
    return bool(query_kw & product_kw)


def _scrape_and_parse(keyword: str, max_candidates: int) -> list[dict]:
    raw_products = playwright_scrape_alibaba(keyword, limit=max_candidates)
    fallback_url = _ALIBABA_SEARCH_URL.format(keyword=keyword.strip().replace(" ", "+"))

    lookups = []
    for p in raw_products:
        if not _is_relevant_product(keyword, p.get("name", "")):
            logger.info("search_part_price: dropping irrelevant product %r for query %r", p.get("name"), keyword)
            continue
        parsed = _parse_alibaba_price(p.get("price"))
        if parsed is None:
            continue
        price_min, price_max = parsed
        lookups.append(
            {
                "part_name": p["name"],
                "price_min": price_min,
                "price_max": price_max,
                "currency": "IDR",
                # Link ke halaman produk spesifik kalau ketemu (lihat
                # findProductUrl di _ALIBABA_EXTRACT_JS) — fallback ke URL
                # search generik hanya kalau product-detail link-nya tidak
                # ditemukan untuk kartu ini (jarang, tapi bisa terjadi untuk
                # tipe kartu produk yang strukturnya berbeda).
                "source_url": p.get("url") or fallback_url,
            }
        )
    return lookups
