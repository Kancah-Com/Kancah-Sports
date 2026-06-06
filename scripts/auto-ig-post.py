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

BUCKET = "ig-posts"

ORANGE = "#ff4d00"
BLACK = "#050505"
WHITE = "#ffffff"

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=football&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=soccer&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=football+transfer&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=premier+league&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=champions+league&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=la+liga&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=serie+a&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=bundesliga&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=timnas+indonesia&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=liga+1+indonesia&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persib&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persija&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persebaya&hl=id&gl=ID&ceid=ID:id",
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


def get_latest_news():
    all_news = []

    for rss in RSS_SOURCES:
        feed = feedparser.parse(rss)

        for item in feed.entries[:20]:
            title = clean_text(item.get("title", ""))
            summary = clean_text(item.get("summary", ""))
            link = item.get("link", "")
            published = item.get("published", "")

            if not title:
                continue

            try:
                pub_date = parsedate_to_datetime(published)
                if pub_date < datetime.now(timezone.utc) - timedelta(hours=48):
                    continue
            except Exception:
                pass

            all_news.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published": published
            })

    if not all_news:
        raise Exception("Tidak ada berita terbaru")

    all_news = list({news["title"]: news for news in all_news}.values())
    all_news.sort(key=lambda x: len(x["title"]), reverse=True)

    print("Total berita:", len(all_news))
    print("Terpilih:", all_news[0]["title"])

    return all_news[0]


def groq_generate(news):
    prompt = f"""
Buat data JSON untuk konten Instagram Kancah Sports.

Pilih template:
- breaking: untuk berita umum, transfer, rumor, update pemain, kabar klub
- quote: jika berita berisi pernyataan/komentar seseorang
- fulltime: jika berita jelas berisi hasil akhir pertandingan dengan skor

Rules:
- Breaking News hanya headline, tanpa subheadline
- Headline maksimal 12 kata
- Headline jangan ALL CAPS
- Quote maksimal 38 kata
- Speaker isi nama orang jika template quote
- image_keyword harus spesifik untuk mencari foto background
- Jangan sebut sumber berita di headline
- Caption 2-4 paragraf pendek
- Hashtag relevan

Berita:
Judul: {news["title"]}
Ringkasan: {news["summary"]}

Balas HANYA JSON valid:
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
  "image_keyword": "...",
  "caption": "...",
  "hashtags": ["#KancahSports"]
}}
"""

    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": "Kamu adalah editor media olahraga. Balas hanya JSON valid."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 350,
            "response_format": {"type": "json_object"}
        },
        timeout=60
    )

    if res.status_code != 200:
        raise Exception(res.text)

    text = res.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(text)
    except Exception:
        print("RAW GROQ:", text)
        return {
            "template_type": "breaking",
            "headline": news["title"][:90],
            "quote": "",
            "speaker": "",
            "home_team": "",
            "away_team": "",
            "home_score": "",
            "away_score": "",
            "competition": "",
            "image_keyword": news["title"],
            "caption": news["summary"],
            "hashtags": ["#KancahSports", "#Football"]
        }


def download_image(url):
    if not url:
        return None

    try:
        r = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        if r.status_code != 200:
            print("Image download failed:", r.status_code, url)
            return None

        return Image.open(io.BytesIO(r.content)).convert("RGBA")

    except Exception as e:
        print("Image error:", e)
        return None


def extract_og_image(article_url):
    if not article_url:
        return None

    try:
        r = requests.get(
            article_url,
            timeout=20,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
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
                "srlimit": 1
            },
            headers=headers,
            timeout=15
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
                "format": "json"
            },
            headers=headers,
            timeout=15
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
                "format": "json"
            },
            headers=headers,
            timeout=20
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


def get_background_image(keyword, source_link=None):
    og_url = extract_og_image(source_link)
    img = download_image(og_url)
    if img:
        return img

    queries = [
        keyword,
        f"{keyword} football",
        f"{keyword} player",
        f"{keyword} soccer"
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


def get_font(size, bold=True):
    paths = [
        "Assets/Ubuntu-Bold.ttf" if bold else "Assets/Ubuntu-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]

    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


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


def fit_multiline(draw, text, max_width, max_height, start_size, min_size, uppercase=False):
    text = str(text)
    if uppercase:
        text = text.upper()

    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, True)
        lines = wrap_text(draw, text, font, max_width)
        line_height = size + 4
        total = len(lines) * line_height

        if total <= max_height:
            return font, lines, line_height

    font = get_font(min_size, True)
    lines = wrap_text(draw, text, font, max_width)
    return font, lines, min_size + 4


def draw_left_multiline(draw, text, x, y, max_width, max_height, start_size=76, min_size=42, fill=WHITE):
    font, lines, line_height = fit_multiline(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        uppercase=False
    )

    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        cy += line_height


def draw_centered(draw, text, x, y, max_width, max_height, start_size=78, min_size=42, fill=WHITE):
    font, lines, line_height = fit_multiline(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        uppercase=False
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
        "fulltime": "Assets/Full-Time.png"
    }

    template_path = template_map.get(template_type, template_map["breaking"])

    bg_keyword = data.get("image_keyword") or data.get("headline") or "football"
    bg_img = get_background_image(bg_keyword, data.get("source_link"))

    if bg_img is None:
        print("Fallback background")
        bg = Image.new("RGBA", (W, H), (20, 20, 20, 255))
    else:
        bg = cover_crop(bg_img, W, H)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 35))
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
            fill=WHITE
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
            fill=BLACK
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
            fill=BLACK
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
            fill=BLACK
        )

    else:
        headline = data.get("headline", "Update terbaru")

        draw_left_multiline(
            draw,
            headline,
            x=58,
            y=965,
            max_width=970,
            max_height=260,
            start_size=72,
            min_size=44,
            fill=WHITE
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
        "Content-Type": "image/jpeg"
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
            "access_token": IG_ACCESS_TOKEN
        },
        timeout=60
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
                "access_token": IG_ACCESS_TOKEN
            },
            timeout=60
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
            "access_token": IG_ACCESS_TOKEN
        },
        timeout=60
    )

    if publish.status_code != 200:
        raise Exception(publish.text)

    print("Instagram published:", publish.json())


def main():
    news = get_latest_news()
    print("News:", news["title"])

    data = groq_generate(news)
    print("Headline:", data.get("headline", ""))

    data["source_link"] = news.get("link", "")

    poster = generate_poster(data)
    image_url = upload_to_supabase(poster)

    hashtags = " ".join(data.get("hashtags", []))
    caption = f'{data.get("caption", news["summary"])}\n\n{hashtags}\n\nSelengkapnya di Kancah Sports.'

    publish_instagram(image_url, caption)


if __name__ == "__main__":
    main()