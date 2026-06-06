import os
import re
import io
import uuid
import html
import textwrap
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

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=timnas+indonesia&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=liga+1+indonesia&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persib&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persija&hl=id&gl=ID&ceid=ID:id"
]

ORANGE = "#ff4d00"
BLACK = "#050505"
WHITE = "#ffffff"
GRAY = "#b8b8b8"

def clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()

def get_latest_news():
    for rss in RSS_SOURCES:
        feed = feedparser.parse(rss)

        for item in feed.entries[:10]:
            title = clean_text(item.get("title", ""))
            summary = clean_text(item.get("summary", ""))
            link = item.get("link", "")
            published = item.get("published", "")

            try:
                pub_date = parsedate_to_datetime(published)
                if pub_date < datetime.now(timezone.utc) - timedelta(hours=12):
                    continue
            except:
                pass

            if title:
                return {
                    "title": title,
                    "summary": summary,
                    "link": link
                }

    raise Exception("Tidak ada berita terbaru <= 12 jam")

def groq_generate(news):
    prompt = f"""
Buat konten Instagram berita olahraga untuk Kancah Sports.

Style:
- Bahasa Indonesia
- Gaya media olahraga modern
- Singkat, tegas, tidak lebay
- Jangan sebut sumber berita
- Jangan pakai disclaimer
- Jangan copy paste judul mentah
- Headline maksimal 7 kata
- Subheadline maksimal 16 kata
- Caption 2-4 paragraf pendek
- Hashtag relevan

Berita:
Judul: {news["title"]}
Ringkasan: {news["summary"]}

Format JSON valid:
{{
  "headline": "...",
  "subheadline": "...",
  "caption": "...",
  "hashtags": ["#KancahSports", "..."]
}}
"""

    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "Kamu adalah editor media olahraga Kancah Sports."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 700
        },
        timeout=60
    )

    if res.status_code != 200:
        raise Exception(res.text)

    text = res.json()["choices"][0]["message"]["content"]

    import json
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0))

def get_font(size, bold=True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]

    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()

def draw_wrapped(draw, text, font, x, y, max_width, fill, line_gap=10):
    words = text.split()
    lines = []
    line = ""

    for word in words:
        test = f"{line} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            line = test
        else:
            lines.append(line)
            line = word

    if line:
        lines.append(line)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap

    return y

def generate_poster(data):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), BLACK)
    draw = ImageDraw.Draw(img)

    # background orange blocks
    draw.rectangle((0, 0, W, 180), fill=ORANGE)
    draw.rectangle((0, 1160, W, H), fill=ORANGE)
    draw.rectangle((60, 240, 1020, 1120), outline=ORANGE, width=4)

    # brand
    brand_font = get_font(58)
    small_font = get_font(26)
    draw.text((60, 52), "KANCAH", font=brand_font, fill=BLACK)
    draw.text((360, 67), "SPORTS.", font=get_font(42), fill=BLACK)

    # label
    draw.rounded_rectangle((60, 230, 260, 285), radius=28, fill=ORANGE)
    draw.text((88, 245), "UPDATE", font=get_font(24), fill=BLACK)

    # headline
    headline = data["headline"].upper()
    subheadline = data["subheadline"]

    y = 340
    y = draw_wrapped(draw, headline, get_font(82), 70, y, 940, WHITE, 14)

    y += 28
    draw.rectangle((70, y, 180, y + 8), fill=ORANGE)
    y += 42

    draw_wrapped(draw, subheadline, get_font(38), 70, y, 900, GRAY, 12)

    # footer
    draw.text((60, 1210), "Kancah Sports", font=get_font(34), fill=BLACK)
    draw.text((60, 1260), "@kancahsports", font=get_font(26), fill=BLACK)

    date_text = datetime.now().strftime("%d.%m.%Y")
    draw.text((830, 1260), date_text, font=get_font(26), fill=BLACK)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
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
    print("Headline:", data["headline"])

    poster = generate_poster(data)
    image_url = upload_to_supabase(poster)

    hashtags = " ".join(data.get("hashtags", []))
    caption = f'{data["caption"]}\n\n{hashtags}\n\nSelengkapnya di Kancah Sports.'

    publish_instagram(image_url, caption)

if __name__ == "__main__":
    main()