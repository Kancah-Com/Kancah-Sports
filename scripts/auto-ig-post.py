import os
import re
import io
import uuid
import html
import json
import time
import requests
import feedparser
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


GROQ_API_KEY = os.environ["GROQ_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

BUCKET = "ig-posts"

BLACK = "#050505"
WHITE = "#ffffff"

GOOD_KEYWORDS = [
    "football", "soccer", "premier league", "champions league",
    "la liga", "serie a", "bundesliga", "transfer", "rumor",
    "arsenal", "chelsea", "liverpool", "manchester city",
    "manchester united", "real madrid", "barcelona", "psg",
    "bayern", "inter", "juventus", "ac milan",
    "timnas indonesia", "liga 1", "persib", "persija",
    "persebaya", "arema", "pss sleman", "ole romeny", "kevin diks",
    "goal", "match", "club", "player", "coach", "manager"
]

BAD_KEYWORDS = [
    "nfl", "american football", "rugby", "basketball", "nba",
    "baseball", "cricket", "tennis", "golf", "ufc", "boxing",
    "betting", "casino", "porn", "nsfw"
]

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=football+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=soccer+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=football+transfer+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=premier+league+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=champions+league+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=la+liga+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=serie+a+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=bundesliga+when:12h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=timnas+indonesia+when:12h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=liga+1+indonesia+when:12h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persib+when:12h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persija+when:12h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persebaya+when:12h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=ole+romeny+when:12h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=kevin+diks+when:12h&hl=id&gl=ID&ceid=ID:id",
]

COUNTRY_CODES = {
    "indonesia": "id",
    "oman": "om",
    "china": "cn",
    "japan": "jp",
    "korea selatan": "kr",
    "australia": "au",
    "argentina": "ar",
    "brazil": "br",
    "france": "fr",
    "germany": "de",
    "spain": "es",
    "italy": "it",
    "england": "gb-eng",
    "netherlands": "nl",
    "portugal": "pt",
}


def clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def normalize_title(title):
    title = clean_text(title)
    title = re.sub(r"\s*-\s*[^-]+$", "", title)
    title = title.replace('"', "'")
    return title.strip()


def detect_main_entity(text):
    text = text.lower()

    entity_map = {
        "persib": "Persib Bandung",
        "persija": "Persija Jakarta",
        "persebaya": "Persebaya Surabaya",
        "arema": "Arema FC",
        "pss sleman": "PSS Sleman",
        "timnas indonesia": "Timnas Indonesia",
        "indonesia": "Timnas Indonesia",
        "ole romeny": "Ole Romeny Timnas Indonesia",
        "kevin diks": "Kevin Diks Timnas Indonesia",
        "arsenal": "Arsenal FC",
        "chelsea": "Chelsea FC",
        "liverpool": "Liverpool FC",
        "manchester city": "Manchester City",
        "manchester united": "Manchester United",
        "real madrid": "Real Madrid",
        "barcelona": "FC Barcelona",
        "psg": "Paris Saint-Germain",
        "bayern": "Bayern Munich",
        "inter": "Inter Milan",
        "juventus": "Juventus",
        "ac milan": "AC Milan",
    }

    for key, value in entity_map.items():
        if key in text:
            return value

    return "football player"


def get_latest_news():
    all_news = []

    BIG_TEAMS = [
        "arsenal",
        "chelsea",
        "liverpool",
        "manchester city",
        "manchester united",
        "real madrid",
        "barcelona",
        "psg",
        "bayern",
        "inter",
        "juventus",
        "ac milan",
        "timnas indonesia",
        "persib",
        "persija",
        "persebaya",
        "arema",
        "pss sleman",
        "bcs",
        "the jakmania",
        "bobotoh",
        "ole romeny",
        "kevin diks",
    ]

    for rss in RSS_SOURCES:
        feed = feedparser.parse(rss)

        for item in feed.entries[:20]:
            title = clean_text(item.get("title", ""))
            summary = clean_text(item.get("summary", ""))
            link = item.get("link", "")
            published = item.get("published", "")

            if not title:
                continue

            combined = f"{title} {summary}".lower()

            if any(bad in combined for bad in BAD_KEYWORDS):
                continue

            if not any(good in combined for good in GOOD_KEYWORDS):
                continue

            try:
                pub_date = parsedate_to_datetime(published)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except Exception:
                pub_date = datetime(2000, 1, 1, tzinfo=timezone.utc)

            if pub_date < datetime.now(timezone.utc) - timedelta(hours=12):
                continue

            all_news.append({
                "title": normalize_title(title),
                "summary": summary,
                "link": link,
                "published": published,
                "pub_date": pub_date,
            })

    if not all_news:
        raise Exception("Tidak ada berita bola terbaru 12 jam terakhir")

    all_news = list({
        news["title"]: news
        for news in all_news
    }.values())

    for news in all_news:
        score = 0
        text = f'{news["title"]} {news["summary"]}'.lower()

        for team in BIG_TEAMS:
            if team in text:
                score += 20

        if "transfer" in text:
            score += 8

        if "resmi" in text or "official" in text:
            score += 8

        if "persib" in text or "timnas indonesia" in text or "indonesia" in text:
            score += 15

        age_hours = (datetime.now(timezone.utc) - news["pub_date"]).total_seconds() / 3600
        recency_score = max(0, 12 - age_hours)
        score += recency_score

        news["score"] = score

    all_news.sort(
        key=lambda x: (
            x["score"],
            x["pub_date"],
        ),
        reverse=True,
    )

    print("Total berita:", len(all_news))
    print("Terpilih:", all_news[0]["title"])
    print("Published:", all_news[0]["published"])
    print("Score:", all_news[0]["score"])

    return all_news[0]


def fallback_data(news):
    title = normalize_title(news.get("title", ""))
    main_entity = detect_main_entity(f'{title} {news.get("summary", "")}')

    words = title.split()
    base_headline = " ".join(words[:18])

    if len(base_headline.split()) < 10:
        headline = f"{base_headline} Jadi Sorotan Baru di Dunia Sepak Bola Hari Ini"
    else:
        headline = base_headline

    return {
        "template_type": "breaking",
        "headline": headline,
        "quote": "",
        "speaker": "",
        "home_team": "",
        "away_team": "",
        "home_score": "",
        "away_score": "",
        "competition": "",
        "image_query": f"{main_entity} football latest match",
        "must_include": [main_entity],
        "avoid": ["logo", "game", "fifa card", "pes", "fc 25"],
        "caption": (
            f"🔥 Lagi ramai dibahas! {headline}\n\n"
            f"Kabar ini jadi salah satu update yang menarik perhatian pecinta sepak bola, "
            f"terutama karena berkaitan dengan perkembangan terbaru yang sedang jadi sorotan.\n\n"
            f"Situasinya masih terus bergerak dan bisa berdampak pada langkah tim maupun pemain terkait ke depannya.\n\n"
            f"Menurut kamu, kabar ini bakal jadi momentum besar atau cuma sekadar lewat saja?"
        ),
        "hashtags": ["#KancahSports", "#Football", "#SepakBola"],
    }


def groq_generate(news):
    main_entity = detect_main_entity(f'{news["title"]} {news["summary"]}')

    prompt = f"""
Buat data JSON untuk konten Instagram Kancah Sports.

Pilih template:
- breaking: untuk berita umum, transfer, rumor, update pemain, kabar klub
- quote: jika berita berisi pernyataan/komentar seseorang
- fulltime: jika berita jelas berisi hasil akhir pertandingan dengan skor

Rules penting:
- Gunakan bahasa Indonesia yang natural, tajam, dan cocok untuk media bola.
- Headline wajib dibuat lebih menarik dan eksploratif.
- Headline minimal 10 kata dan ideal 12-18 kata.
- Headline harus cukup panjang agar tampil minimal 2 baris di poster.
- Jangan terlalu pendek seperti judul mentah RSS.
- Jangan ALL CAPS.
- Jangan pakai tanda kutip dua di dalam value JSON.
- Jika ada judul acara pakai tanda petik satu saja.
- Jangan buat headline list/rangkuman seperti A, B, dan C.
- Breaking News tetap hanya headline, tanpa subheadline.
- Headline harus fokus SATU berita utama saja.
- Caption wajib panjang, engaging, dan punya hook di kalimat pertama.
- Caption 4-6 paragraf pendek.
- Caption harus bikin pembaca penasaran untuk baca berita lengkap.
- Caption jangan terlalu kaku.
- Caption boleh pakai emoji secukupnya.
- Hashtag relevan dan jangan terlalu banyak.

Rules gambar:
- image_query wajib sangat spesifik untuk mencari foto background yang relevan.
- Entitas utama berita terdeteksi: {main_entity}
- Jika berita tentang Persib, image_query harus mengandung Persib Bandung.
- Jika berita tentang Persija, image_query harus mengandung Persija Jakarta.
- Jika berita tentang pemain, image_query harus berisi nama pemain + klub/tim.
- Jika berita tentang klub, image_query harus berisi nama klub lengkap.
- Jika berita tentang tim nasional, image_query harus berisi nama pemain/tim + national team.
- Jangan pakai image_query umum seperti football atau soccer.
- must_include wajib berisi nama klub/pemain utama.
- avoid berisi klub/pemain/topik yang tidak relevan.
- image_query jangan berupa judul berita panjang.

Berita:
Judul: {news["title"]}
Ringkasan: {news["summary"]}

Balas HANYA JSON valid tanpa markdown:
{{
  "template_type": "breaking",
  "headline": "...",
  "quote": "",
  "speaker": "",
  "home_team": "",
  "away_team": "",
  "home_score": "",
  "away_score": "",
  "competition": "",
  "image_query": "...",
  "must_include": ["{main_entity}"],
  "avoid": ["logo", "game", "fifa card"],
  "caption": "...",
  "hashtags": ["#KancahSports", "#SepakBola"]
}}
"""

    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system",
                    "content": "Balas hanya JSON valid. Jangan markdown.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "response_format": {
                "type": "json_object",
            },
            "temperature": 0.45,
            "max_tokens": 900,
        },
        timeout=60,
    )

    if res.status_code != 200:
        print("Groq error:", res.text)
        return fallback_data(news)

    text = res.json()["choices"][0]["message"]["content"]

    try:
        data = json.loads(text)
    except Exception as e:
        print("RAW GROQ:", text)
        print("JSON parse error:", e)
        return fallback_data(news)

    if not data.get("headline"):
        data["headline"] = fallback_data(news)["headline"]

    if len(data["headline"].split()) < 10:
        data["headline"] = f'{data["headline"]} Jadi Sorotan Besar Pecinta Sepak Bola Hari Ini'

    if not data.get("image_query"):
        data["image_query"] = f"{main_entity} football latest match"

    if not data.get("must_include"):
        data["must_include"] = [main_entity]

    if not data.get("avoid"):
        data["avoid"] = ["logo", "game", "fifa card", "pes", "fc 25"]

    if not data.get("caption"):
        data["caption"] = fallback_data(news)["caption"]

    if not data.get("hashtags"):
        data["hashtags"] = ["#KancahSports", "#SepakBola", "#Football"]

    return data


def serper_image_search(query, must_include=None, avoid=None):
    if not SERPER_API_KEY:
        print("SERPER_API_KEY kosong, skip Serper image search")
        return None

    must_include = [x.lower() for x in (must_include or [])]
    avoid = [x.lower() for x in (avoid or [])]

    try:
        r = requests.post(
            "https://google.serper.dev/images",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 10},
            timeout=20,
        )

        if r.status_code != 200:
            print("Serper error:", r.text)
            return None

        images = r.json().get("images", [])
        best = None
        best_score = -999

        for item in images:
            url = item.get("imageUrl", "")
            title = item.get("title", "")
            source = item.get("source", "")
            haystack = f"{url} {title} {source}".lower()

            if any(a in haystack for a in avoid):
                continue

            score = 0

            for m in must_include:
                if m and m in haystack:
                    score += 8

            query_words = query.lower().split()
            for word in query_words:
                if len(word) > 3 and word in haystack:
                    score += 1

            width = item.get("imageWidth") or 0
            height = item.get("imageHeight") or 0

            if width >= 800 and height >= 800:
                score += 3

            if width >= 1080 or height >= 1080:
                score += 2

            if "logo" in haystack or "icon" in haystack:
                score -= 10

            if score > best_score:
                best_score = score
                best = url

        if best:
            print("Serper image:", best)
            print("Image score:", best_score)
            return best

    except Exception as e:
        print("Serper image error:", e)

    return None


def download_image(url):
    if not url:
        return None

    try:
        r = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        if r.status_code != 200:
            print("Image download failed:", r.status_code, url)
            return None

        return Image.open(io.BytesIO(r.content)).convert("RGBA")

    except Exception as e:
        print("Image error:", e)
        return None


def resolve_google_news_url(url):
    if not url or "news.google.com" not in url:
        return url

    try:
        r = requests.get(
            url,
            timeout=20,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        final_url = r.url
        print("Resolved URL:", final_url)
        return final_url

    except Exception as e:
        print("Resolve Google News URL error:", e)
        return url


def extract_og_image(article_url):
    if not article_url:
        return None

    try:
        real_url = resolve_google_news_url(article_url)

        if "news.google.com" in real_url:
            print("Still Google News URL, skip OG")
            return None

        r = requests.get(
            real_url,
            timeout=20,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        html_text = r.text

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, html_text, re.I)
            if match:
                img = html.unescape(match.group(1))
                print("OG image:", img)
                return img

    except Exception as e:
        print("OG image error:", e)

    return None


def wikipedia_image(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        search = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            headers=headers,
            timeout=15,
        )

        results = search.json().get("query", {}).get("search", [])
        if not results:
            return None

        page_title = results[0]["title"]

        img = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": page_title,
                "prop": "pageimages",
                "pithumbsize": 1600,
                "format": "json",
            },
            headers=headers,
            timeout=15,
        )

        pages = img.json().get("query", {}).get("pages", {})
        for page in pages.values():
            src = page.get("thumbnail", {}).get("source")
            if src:
                return src

    except Exception as e:
        print("Wikipedia image error:", e)

    return None


def commons_image(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 6,
                "gsrlimit": 8,
                "prop": "imageinfo",
                "iiprop": "url|mime|size",
                "format": "json",
            },
            headers=headers,
            timeout=20,
        )

        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            url = info.get("url")
            mime = info.get("mime", "")
            width = info.get("width", 0)

            if url and width >= 700 and mime.startswith("image/"):
                return url

    except Exception as e:
        print("Commons image error:", e)

    return None


def get_background_image(keyword, source_link=None, must_include=None, avoid=None):
    must_include = must_include or []
    avoid = avoid or []

    print("Image query:", keyword)
    print("Must include:", must_include)
    print("Avoid:", avoid)

    serper_url = serper_image_search(
        keyword,
        must_include=must_include,
        avoid=avoid + ["logo", "icon", "fifa card", "pes", "fc 25", "game"],
    )

    img = download_image(serper_url)
    if img:
        return img

    og_url = extract_og_image(source_link)

    img = download_image(og_url)
    if img:
        return img

    queries = [
        keyword,
        f"{keyword} football player",
        f"{keyword} football club",
        f"{keyword} latest match",
    ]

    for q in queries:
        img_url = wikipedia_image(q)
        img = download_image(img_url)
        if img:
            return img

    for q in queries:
        img_url = commons_image(q)
        img = download_image(img_url)
        if img:
            return img

    return None


def get_team_logo(team_name):
    name = (team_name or "").lower().strip()

    for key, code in COUNTRY_CODES.items():
        if key in name:
            return download_image(f"https://flagcdn.com/w320/{code}.png")

    img = download_image(wikipedia_image(f"{team_name} football club logo"))
    if img:
        return img

    img = download_image(commons_image(f"{team_name} logo football"))
    if img:
        return img

    return None


def cover_crop(image, width=1080, height=1350):
    img = image.convert("RGB")
    ratio = img.width / img.height
    target = width / height

    if ratio > target:
        new_h = height
        new_w = int(height * ratio)
    else:
        new_w = width
        new_h = int(width / ratio)

    img = img.resize((new_w, new_h))
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return img.crop((left, top, left + width, top + height)).convert("RGBA")


def get_font(size, weight="bold"):
    font_map = {
        "bold": "Assets/Fonts/Ubuntu-Bold.ttf",
        "medium": "Assets/Fonts/Ubuntu-Medium.ttf",
        "regular": "Assets/Fonts/Ubuntu-Regular.ttf",
    }

    path = font_map.get(weight, font_map["bold"])

    if os.path.exists(path):
        return ImageFont.truetype(path, size)

    fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    return ImageFont.truetype(fallback, size)


def wrap_text(draw, text, font, max_width):
    words = str(text).split()
    lines = []
    line = ""

    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word

    if line:
        lines.append(line)

    return lines


def fit_multiline(draw, text, max_width, max_height, start_size, min_size, weight="bold", uppercase=False):
    text = str(text)
    if uppercase:
        text = text.upper()

    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, weight)
        lines = wrap_text(draw, text, font, max_width)
        line_height = size + 4
        total = len(lines) * line_height

        if total <= max_height:
            return font, lines, line_height

    font = get_font(min_size, weight)
    lines = wrap_text(draw, text, font, max_width)
    return font, lines, min_size + 4


def draw_left_multiline(draw, text, x, y, max_width, max_height, start_size=76, min_size=42, fill=WHITE, weight="bold"):
    font, lines, line_height = fit_multiline(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        weight=weight,
        uppercase=False,
    )

    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        cy += line_height


def draw_centered(draw, text, x, y, max_width, max_height, start_size=78, min_size=42, fill=WHITE, weight="bold"):
    font, lines, line_height = fit_multiline(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        weight=weight,
        uppercase=False,
    )

    total_height = len(lines) * line_height
    cy = y + (max_height - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        draw.text((x + (max_width - lw) // 2, cy), line, font=font, fill=fill)
        cy += line_height


def paste_contain(base, logo, center_x, center_y, max_w, max_h):
    if logo is None:
        return

    logo = logo.convert("RGBA")
    ratio = min(max_w / logo.width, max_h / logo.height)
    nw = int(logo.width * ratio)
    nh = int(logo.height * ratio)
    logo = logo.resize((nw, nh))

    x = int(center_x - nw / 2)
    y = int(center_y - nh / 2)
    base.alpha_composite(logo, (x, y))


def generate_poster(data):
    W, H = 1080, 1350
    template_type = data.get("template_type", "breaking").lower()

    template_map = {
        "breaking": "Assets/Breaking-News.png",
        "quote": "Assets/Quotes.png",
        "fulltime": "Assets/Full-Time.png",
    }

    template_path = template_map.get(template_type, template_map["breaking"])

    bg_keyword = (
        data.get("image_query")
        or data.get("image_keyword")
        or data.get("headline")
        or "football player"
    )

    bg_img = get_background_image(
        bg_keyword,
        data.get("source_link"),
        must_include=data.get("must_include", []),
        avoid=data.get("avoid", []),
    )

    if bg_img is None:
        print("Fallback background")
        bg = Image.new("RGBA", (W, H), (20, 20, 20, 255))
    else:
        bg = cover_crop(bg_img, W, H)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 25))
    bg.alpha_composite(overlay)

    if os.path.exists(template_path):
        template = Image.open(template_path).convert("RGBA").resize((W, H))
        bg.alpha_composite(template)
    else:
        print("Template not found:", template_path)

    draw = ImageDraw.Draw(bg)

    if template_type == "quote":
        quote = data.get("quote") or data.get("headline") or ""
        speaker = data.get("speaker") or ""

        draw_centered(
            draw,
            f'"{quote}"',
            x=80,
            y=650,
            max_width=920,
            max_height=290,
            start_size=48,
            min_size=30,
            fill=WHITE,
            weight="regular",
        )

        draw_centered(
            draw,
            speaker,
            x=140,
            y=955,
            max_width=800,
            max_height=90,
            start_size=34,
            min_size=24,
            fill=BLACK,
            weight="medium",
        )

    elif template_type == "fulltime":
        home = data.get("home_team", "")
        away = data.get("away_team", "")
        hs = data.get("home_score", "")
        aw = data.get("away_score", "")
        comp = data.get("competition", "")

        home_logo = get_team_logo(home)
        away_logo = get_team_logo(away)

        paste_contain(bg, home_logo, 345, 740, 130, 130)
        paste_contain(bg, away_logo, 735, 740, 130, 130)

        score_text = f"{hs} - {aw}" if hs and aw else data.get("headline", "Full Time")

        draw_centered(
            draw,
            score_text,
            x=360,
            y=665,
            max_width=360,
            max_height=145,
            start_size=82,
            min_size=42,
            fill=BLACK,
            weight="bold",
        )

        draw_centered(
            draw,
            comp,
            x=180,
            y=855,
            max_width=720,
            max_height=80,
            start_size=36,
            min_size=24,
            fill=BLACK,
            weight="medium",
        )

    else:
        headline = data.get("headline", "Update terbaru")

        draw_left_multiline(
            draw,
            headline,
            x=58,
            y=955,
            max_width=970,
            max_height=260,
            start_size=62,
            min_size=34,
            fill=WHITE,
            weight="bold",
        )

    out = io.BytesIO()
    bg.convert("RGB").save(out, format="JPEG", quality=95)
    out.seek(0)
    return out


def upload_to_supabase(image_bytes):
    filename = f"ig-{uuid.uuid4().hex}.jpg"
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{filename}"

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "image/jpeg",
    }

    res = requests.post(url, headers=headers, data=image_bytes.getvalue())

    if res.status_code not in [200, 201]:
        raise Exception(res.text)

    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{filename}"


def publish_instagram(image_url, caption):
    create = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=60,
    )

    if create.status_code != 200:
        raise Exception(create.text)

    creation_id = create.json()["id"]
    print("Creation ID:", creation_id)

    for _ in range(10):
        status = requests.get(
            f"https://graph.facebook.com/v25.0/{creation_id}",
            params={
                "fields": "status_code",
                "access_token": IG_ACCESS_TOKEN,
            },
            timeout=60,
        )

        print("Media status:", status.text)

        try:
            status_code = status.json().get("status_code")
        except Exception:
            status_code = None

        if status_code == "FINISHED":
            break

        time.sleep(10)

    publish = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=60,
    )

    if publish.status_code != 200:
        raise Exception(publish.text)

    print("Instagram published:", publish.json())


def main():
    news = get_latest_news()
    print("News:", news["title"])

    data = groq_generate(news)
    print("Headline:", data.get("headline", ""))
    print("Image query:", data.get("image_query", ""))
    print("Caption:", data.get("caption", ""))

    data["source_link"] = news.get("link", "")

    poster = generate_poster(data)
    image_url = upload_to_supabase(poster)

    hashtags = " ".join(data.get("hashtags", []))
    caption = f'{data.get("caption", news["summary"])}\n\n{hashtags}\n\nSelengkapnya di Kancah Sports.'

    publish_instagram(image_url, caption)


if __name__ == "__main__":
    main()