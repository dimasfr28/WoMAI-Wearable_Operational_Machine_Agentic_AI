"""SearXNG search + Firecrawl scrape -> part price lookup — Section 6.10.

Revisi rancangan.txt: harga part HARUS dicari dari platform e-commerce
(shopee, tokopedia, alibaba, lazada dll), bukan manual servis resmi vendor,
forum, eBay, dll — sumber-sumber itu tidak punya harga jual konsisten dan
tidak merepresentasikan biaya penggantian part yang sebenarnya bisa dibeli.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Pola teks yang menandakan Firecrawl BERHASIL scrape (tidak exception, ada
# konten), tapi kontennya adalah halaman blokir bot-detection / login wall,
# bukan halaman produk — ditemukan lewat testing nyata: Alibaba kadang
# mengembalikan "Sorry, we have detected unusual traffic from your network."
# untuk URL & waktu yang sama persis dengan percobaan sebelumnya yang sukses,
# jadi ini transient (worth retrying), bukan blokir permanen per-URL.
_BLOCKED_PAGE_PATTERNS = (
    "unusual traffic",
    "masuk untuk kemudahan bertransaksi",
    "verify you are human",
    "captcha",
    "access denied",
    "akses ditolak",
)


def _looks_blocked(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(p in lowered for p in _BLOCKED_PAGE_PATTERNS)

# Domain e-commerce yang diizinkan sebagai sumber harga part — 4 yang eksplisit
# disebut di rancangan.txt (shopee/tokopedia/alibaba/lazada) + marketplace
# sejenis yang umum dipakai untuk cari part CNC/mesin di Indonesia/regional.
# Dicocokkan terhadap `netloc` URL (lihat _is_ecommerce_url), jadi subdomain
# (mis. m.shopee.co.id) otomatis ikut cocok karena endswith.
ECOMMERCE_DOMAINS = (
    "shopee.co.id",
    "shopee.com",
    "tokopedia.com",
    "lazada.co.id",
    "lazada.com",
    "alibaba.com",
    "aliexpress.com",
    "bukalapak.com",
    "blibli.com",
    "jd.id",
)


def _is_ecommerce_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in ECOMMERCE_DOMAINS)


def searxng_search(query_text: str, num_results: int = 5, ecommerce_only: bool = False) -> list[dict]:
    """Search SearXNG for candidate URLs. Returns [{"title", "url", "content"}, ...].

    ecommerce_only=True restricts results to ECOMMERCE_DOMAINS (used by
    search_part_price) — filtered AFTER the query rather than relying solely
    on the `site:` operator in the query text, since SearXNG doesn't always
    honor multi-site OR queries consistently across all its backing engines.
    """
    try:
        resp = httpx.get(
            f"{settings.SEARXNG_BASE_URL}/search",
            params={"q": query_text, "format": "json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if ecommerce_only:
            results = [r for r in results if _is_ecommerce_url(r.get("url", ""))]
        results = results[:num_results]
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in results
        ]
    except Exception:
        logger.exception("searxng_search failed for query=%r", query_text)
        return []


_ALIBABA_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


def _alibaba_cookies() -> dict[str, str] | None:
    if not settings.ALIBABA_COOKIES:
        return None
    try:
        import json

        return json.loads(settings.ALIBABA_COOKIES)
    except Exception:
        logger.exception("_alibaba_cookies: gagal parse ALIBABA_COOKIES sebagai JSON")
        return None


def alibaba_direct_scrape(url: str) -> str | None:
    """Scrape langsung alibaba.com pakai `requests` + cookie sesi login (BUKAN
    lewat Firecrawl) — ditemukan via testing nyata bahwa Alibaba menyajikan
    halaman anti-bot JS challenge ("<punish-component />") ke request TANPA
    cookie login, baik lewat requests polos maupun Firecrawl (browser
    headless), tapi request DENGAN cookie sesi yang sudah login konsisten
    lolos dan mendapat HTML lengkap berisi harga produk asli — tertanam
    sebagai JSON SSR data per kartu produk (lihat _ALIBABA_JSON_PRODUCT_RE
    di _extract_products_from_text, yang dijalankan di atas HTML mentah ini).

    Cookie session AKAN expired berkala — kalau ALIBABA_COOKIES kosong atau
    sudah tidak valid lagi, fungsi ini mengembalikan None dan caller
    (_search_and_lookup_prices) jatuh ke firecrawl_scrape_with_retry seperti
    sebelumnya."""
    cookies = _alibaba_cookies()
    if cookies is None:
        return None
    try:
        import requests

        resp = requests.get(url, headers={"User-Agent": _ALIBABA_USER_AGENT}, cookies=cookies, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception:
        logger.exception("alibaba_direct_scrape failed for url=%r", url)
        return None


def firecrawl_scrape(url: str) -> str | None:
    """Scrape a URL via Firecrawl, returning extracted markdown/text, or None on failure.

    Ditemukan via testing nyata: halaman Alibaba tertentu butuh render Playwright
    berat dan genuinely timeout di sisi Firecrawl sendiri (error "SCRAPE_TIMEOUT",
    bukan bot-detection) sekitar detik ke-30. httpx timeout SEBELUMNYA juga 30.0 —
    persis sama dengan timeout internal Firecrawl — sehingga httpx sering timeout
    duluan sepersekian detik sebelum Firecrawl sempat mengirim response error yang
    rapi, membuang exception generik alih-alih hasil yang jelas. Timeout httpx
    diberi jeda ekstra (45s) supaya selalu Firecrawl yang menyerah duluan."""
    try:
        headers = {}
        if settings.FIRECRAWL_API_KEY:
            headers["Authorization"] = f"Bearer {settings.FIRECRAWL_API_KEY}"
        resp = httpx.post(
            f"{settings.FIRECRAWL_API_URL}/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers=headers,
            timeout=45.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("markdown") or data.get("markdown")
    except Exception:
        logger.exception("firecrawl_scrape failed for url=%r", url)
        return None


def firecrawl_scrape_with_retry(url: str, max_attempts: int = 3, retry_delay_seconds: float = 3.0) -> str | None:
    """firecrawl_scrape(), tapi retry kalau hasilnya "sukses" secara HTTP namun
    isinya ternyata halaman bot-detection/login (lihat _looks_blocked) —
    ditemukan lewat testing nyata bahwa blokir Alibaba TIDAK konsisten: URL
    yang sama bisa sukses di satu percobaan lalu terblokir di percobaan
    berikutnya (dan sebaliknya), jadi transient error yang layak di-retry,
    bukan kegagalan permanen per-URL."""
    last_result = None
    for attempt in range(1, max_attempts + 1):
        result = firecrawl_scrape(url)
        last_result = result
        if result is not None and not _looks_blocked(result):
            return result
        if attempt < max_attempts:
            logger.warning(
                "firecrawl_scrape_with_retry: attempt %d/%d for %r returned a blocked/empty page, retrying",
                attempt, max_attempts, url,
            )
            time.sleep(retry_delay_seconds)
    return last_result


# Harga dianggap masuk akal untuk part CNC industrial (dalam IDR, setelah
# konversi) kalau dalam rentang ini — menyaring kecocokan regex palsu (ongkir
# "Rp5.000", diskon generik, dll) yang lolos pola tapi jelas bukan harga part.
_MIN_PLAUSIBLE_PRICE = 10_000
_MAX_PLAUSIBLE_PRICE = 500_000_000


def _parse_idr_price_str(raw: str) -> tuple[float, float] | None:
    """Parse satu representasi harga Rupiah — bisa titik tunggal
    ("Rp85.088.126" -> (85088126, 85088126)) atau rentang harga varian produk
    ("Rp73.307-274.898" -> (73307, 274898)), umum untuk listing yang punya
    beberapa varian/ukuran dalam satu kartu produk. Mengembalikan (min, max)
    supaya kedua ujung rentang varian ikut tersimpan, bukan cuma titik bawah."""
    parts = re.split(r"[-–]", raw.strip())
    values = []
    for p in parts:
        numeric = re.sub(r"[^\d]", "", p)
        if not numeric:
            continue
        try:
            values.append(float(numeric))
        except ValueError:
            continue
    if not values:
        return None
    lo, hi = min(values), max(values)
    if not (_MIN_PLAUSIBLE_PRICE <= lo <= _MAX_PLAUSIBLE_PRICE):
        return None
    return (lo, hi)


# Pola 1: halaman DETAIL/SEARCH Alibaba (mis. es929-spindle.html) — data produk
# tertanam sebagai JSON SSR di dalam <script>, satu blok per kartu produk berisi
# "title" (nama produk, kadang dibungkus <span class=keywords>...) lalu beberapa
# ratus karakter kemudian "promotionInfoVO":{...,"localOriginalPriceRangeStr":
# "Rp...",...}. Ditemukan lewat inspeksi HTML mentah langsung (lihat riwayat
# investigasi bot-detection Alibaba) — struktur ini spesifik alibaba.com/
# indonesian.alibaba.com, tidak berlaku di marketplace lain.
_ALIBABA_JSON_PRODUCT_RE = re.compile(
    r'"title":"((?:[^"\\]|\\.)*)"\}.{0,300}?"localOriginalPriceRangeStr":"([^"]+)"',
    re.DOTALL,
)

# Pola 2: halaman KATALOG KATEGORI Alibaba (mis. lathe-linear-guide-rail.html)
# — markup HTML langsung, bukan JSON: <h2 style="display:inline">Nama Produk
# </h2> diikuti sebuah <div data-component="ProductPrice">Rp...</div> dalam
# beberapa ratus karakter setelahnya.
_ALIBABA_HTML_PRODUCT_RE = re.compile(
    r'<h2 style="display:\s*inline;?">([^<]+)</h2>.{0,500}?data-component="ProductPrice">([^<]+)<',
    re.DOTALL,
)

# Pola 3: Firecrawl markdown Tokopedia (dan marketplace lokal sejenis) — nama
# produk sebagai baris teks biasa (bukan gambar/link), lalu "\\\n\\\nRp..." pada
# baris berikutnya (artefak markdown Firecrawl: paragraf dipisah "\" + newline).
# Grup 2 di sini TIDAK menyertakan "Rp" (sudah dikonsumsi regex-nya sendiri),
# beda dari dua pola Alibaba di atas yang grup harganya sudah "Rp...".
_TOKOPEDIA_MD_PRODUCT_RE = re.compile(r"\n([A-Za-z][^\n\[\]!]{10,150})\\\n\\\nRp([\d.,]+)")


def _extract_products_from_text(text: str, max_products: int = 4) -> list[dict]:
    """Ekstrak produk INDIVIDUAL (nama + harga) dari halaman katalog/listing,
    bukan sekadar kumpulan angka harga lepas — user secara eksplisit minta tiap
    baris hasil menyebut produk spesifik apa yang harganya segitu, bukan cuma
    "part_name generik: Rp X - Rp Y" hasil gabungan banyak listing berbeda.

    Coba 3 pola berurutan (lihat masing-masing regex di atas), pakai yang
    PERTAMA menghasilkan match — satu halaman hanya punya satu struktur yang
    relevan, mencoba pola lain di halaman yang sama biasanya sia-sia. Kalau
    TIDAK ADA pola yang cocok sama sekali, kembalikan list kosong: caller tidak
    boleh fallback ke nama generik (instruksi eksplisit — "jika tidak bisa
    di-scrape maka jangan tampilkan apapun")."""
    for pattern, price_group_has_rp_prefix in (
        (_ALIBABA_JSON_PRODUCT_RE, True),
        (_ALIBABA_HTML_PRODUCT_RE, True),
        (_TOKOPEDIA_MD_PRODUCT_RE, False),
    ):
        matches = pattern.findall(text)
        if not matches:
            continue

        products = []
        seen_names = set()
        for name_raw, price_raw in matches:
            name = re.sub(r"<[^>]+>", "", name_raw).strip()
            if not name or name in seen_names:
                continue
            price_str = price_raw if price_group_has_rp_prefix else f"Rp{price_raw}"
            parsed = _parse_idr_price_str(price_str)
            if parsed is None:
                continue
            price_min, price_max = parsed
            seen_names.add(name)
            products.append({"name": name, "price_min": price_min, "price_max": price_max})
            if len(products) >= max_products:
                break
        if products:
            return products
    return []


def search_part_price(part_name: str, machine_type: str = "Haas CNC", max_candidates: int = 3) -> list[dict]:
    """Full Section 6.10 flow steps 2-4: search -> scrape -> extract produk individual.

    Revisi rancangan.txt: hasil DIBATASI ke platform e-commerce saja (lihat
    ECOMMERCE_DOMAINS) — manual servis resmi, forum, eBay, dll tidak boleh jadi
    sumber harga. `site:` di query text steers SearXNG's own ranking toward
    those domains up front; ecommerce_only=True in searxng_search then hard-
    filters whatever comes back, since `site:` isn't honored by every engine
    SearXNG queries.

    Revisi terbaru (instruksi eksplisit user): link yang muncul adalah halaman
    KATALOG (banyak produk sekaligus, mis. Tokopedia "/find/bearing-cnc" atau
    halaman search Alibaba), bukan satu produk — jadi output sekarang adalah
    DAFTAR PRODUK INDIVIDUAL (nama spesifik + harga masing-masing, sampai 4 per
    kandidat URL), BUKAN satu baris "part_name generik: Rp X - Rp Y" hasil
    gabungan banyak listing berbeda seperti sebelumnya. Kalau sebuah URL sama
    sekali tidak bisa di-scrape ATAU hasil scrape-nya tidak mengandung struktur
    produk yang bisa dikenali (lihat _extract_products_from_text's 3 pola),
    URL itu di-SKIP TOTAL — tidak menghasilkan baris "tidak ditemukan" apa pun.
    Snippet SearXNG TIDAK dipakai lagi sebagai sumber harga di sini: snippet
    cuma deskripsi kategori generik, tidak pernah punya struktur nama+harga per
    produk yang bisa dipertanggungjawabkan sebagai "produk spesifik ini harganya
    segini" — memakainya akan melanggar instruksi "jangan tampilkan apapun"
    kalau tidak benar-benar bisa di-scrape.

    Revisi sebelumnya (ditemukan via testing langsung, tetap relevan untuk
    proses scrape-nya): Firecrawl kadang scrape "sukses" (HTTP 200, ada
    markdown) tapi isinya adalah halaman bot-detection Alibaba ("Sorry, we
    have detected unusual traffic...") atau login-wall, BUKAN exception.
    `firecrawl_scrape_with_retry` + `_looks_blocked` menangani ini (retry
    beberapa kali, buang hasil kalau tetap halaman blokir). Untuk Alibaba
    khususnya, `alibaba_direct_scrape` (requests + cookie sesi login) dicoba
    LEBIH DULU karena jauh lebih tahan terhadap anti-bot JS challenge
    dibanding Firecrawl (lihat docstring-nya).

    Kalau ronde pertama (query spesifik part_name+machine_type) tidak
    menghasilkan satu produk pun, otomatis coba satu ronde lagi dengan query
    lebih longgar (part_name saja) untuk menjaring kandidat URL lain.

    Returns list of {"part_name" (nama produk SPESIFIK, bukan nama part yang
    dicari), "price_min", "price_max", "currency", "source_url"} — bisa kosong
    kalau SearXNG tidak tersedia, atau tidak ada satupun kandidat yang berhasil
    di-scrape dengan struktur produk yang dikenali.
    """
    site_filter = " OR ".join(f"site:{d}" for d in ECOMMERCE_DOMAINS)

    query_text = f"harga {part_name} {machine_type} ({site_filter})"
    lookups = _search_and_lookup_prices(query_text, max_candidates)

    if not lookups:
        broader_query = f"harga {part_name} ({site_filter})"
        if broader_query != query_text:
            logger.info("search_part_price: no products from specific query, retrying broader query=%r", broader_query)
            lookups = _search_and_lookup_prices(broader_query, max_candidates)

    return lookups


def _search_and_lookup_prices(query_text: str, max_candidates: int) -> list[dict]:
    """One search->scrape->extract round for a given query_text — factored out
    of search_part_price so it can be called twice (specific query, then a
    broader fallback query) without duplicating the scrape/extract logic."""
    candidates = searxng_search(query_text, num_results=max_candidates, ecommerce_only=True)

    lookups = []
    for c in candidates:
        url = c.get("url")
        if not url:
            continue

        # Alibaba: coba jalur requests+cookie-login dulu (jauh lebih tahan
        # terhadap anti-bot JS challenge, lihat alibaba_direct_scrape's
        # docstring) — fallback ke Firecrawl kalau cookie tidak tersedia/gagal.
        scraped = None
        if "alibaba.com" in urlparse(url).netloc.lower():
            scraped = alibaba_direct_scrape(url)
        if scraped is None or _looks_blocked(scraped):
            scraped = firecrawl_scrape_with_retry(url)
        if scraped is not None and _looks_blocked(scraped):
            logger.warning("_search_and_lookup_prices: %r still looked blocked after retries, skipping", url)
            scraped = None

        if not scraped:
            continue  # tidak bisa di-scrape sama sekali -> skip total, tidak ada baris apa pun

        products = _extract_products_from_text(scraped)
        if not products:
            continue  # bisa di-scrape, tapi tidak ada struktur produk yang dikenali -> skip total

        for p in products:
            lookups.append(
                {
                    "part_name": p["name"],
                    "price_min": p["price_min"],
                    "price_max": p["price_max"],
                    "currency": "IDR",
                    "source_url": url,
                }
            )
    return lookups
