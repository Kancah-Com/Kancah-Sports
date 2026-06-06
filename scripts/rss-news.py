import os
import re
import html
import random
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

RSS_SOURCES = [
    {
        "name": "Google News Timnas",
        "url": "https://news.google.com/rss/search?q=timnas+indonesia&hl=id&gl=ID&ceid=ID:id",
        "category": "Football"
    },
    {
        "name": "Google News Liga 1",
        "url": "https://news.google.com/rss/search?q=liga+1+indonesia&hl=id&gl=ID&ceid=ID:id",
        "category": "Football"
    }
]

FALLBACK_IMAGES = {
    "Football": [
        "https://images.unsplash.com/photo-1579952363873-27f3bade9f55?q=90&w=1600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517466787929-bc90951d0974?q=90&w=1600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1522778119026-d647f0596c20?q=90&w=1600&auto=format&fit=crop"
    ],
    "Sports": [
        "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?q=90&w=1600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517649763962-0c623066013b?q=90&w=1600&auto=format&fit=crop"
    ]
}

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:120]

def clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()

def normalize_title(title):
    title = clean_text(title)
    title = re.sub(r"\s+-\s+[^-]+$", "", title)
    return title.strip()

def detect_category(title, summary):
    text = f"{title} {summary}".lower()

    if any(k in text for k in ["timnas", "persib", "persija", "liga", "sepak bola", "pssi", "fifa", "afc"]):
        return "Football"

    return "Sports"

def extract_entity(title):
    lower = title.lower()

    mapping = {
        "timnas indonesia": "Tim nasional sepak bola Indonesia",
        "persib": "Persib Bandung",
        "persija": "Persija Jakarta",
        "arema": "Arema FC",
        "persebaya": "Persebaya Surabaya",
        "ole romeny": "Ole Romeny",
        "erick thohir": "Erick Thohir",
        "pssi": "PSSI",
        "afc": "Asian Football Confederation",
        "fifa": "FIFA"
    }

    for key, value in mapping.items():
        if key in lower:
            return value

    words = re.findall(r"[A-Za-z0-9]+", title)
    stop = {
        "dan", "yang", "dari", "dalam", "untuk", "dengan",
        "hasil", "jadwal", "profil", "mengenal", "cara",
        "aturan", "berikut", "simak", "ini", "pertandingan",
        "timnas", "indonesia"
    }

    clean_words = [w for w in words if len(w) > 3 and w.lower() not in stop]
    return " ".join(clean_words[:4]) or title

def image_already_used(image_url):
    try:
        url = f"{SUPABASE_URL}/rest/v1/articles"
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"
        }

        response = requests.get(
            url,
            headers=headers,
            params={
                "select": "id",
                "image_url": f"eq.{image_url}",
                "limit": 1
            },
            timeout=15
        )

        if response.status_code != 200:
            return False

        return len(response.json()) > 0

    except Exception:
        return False

def wikipedia_image(query):
    try:
        headers = {
            "User-Agent": "KancahSportsBot/1.0 (kancahcreative@gmail.com)"
        }

        search = requests.get(
            "https://id.wikipedia.org/w/api.php",
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

        if search.status_code != 200:
            return None

        results = search.json().get("query", {}).get("search", [])
        if not results:
            return None

        page_title = results[0]["title"]

        image = requests.get(
            "https://id.wikipedia.org/w/api.php",
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

        pages = image.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            img = thumb.get("source")
            if img:
                return img

    except Exception as e:
        print("Wikipedia image error:", e)

    return None

def commons_image(query):
    try:
        headers = {
            "User-Agent": "KancahSportsBot/1.0 (kancahcreative@gmail.com)"
        }

        response = requests.get(
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
            timeout=15
        )

        if response.status_code != 200:
            return None

        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            img = info.get("url")
            width = info.get("width", 0)
            mime = info.get("mime", "")

            if img and width >= 700 and mime.startswith("image/"):
                return img

    except Exception as e:
        print("Commons image error:", e)

    return None

def random_cover(category):
    images = FALLBACK_IMAGES.get(category, FALLBACK_IMAGES["Sports"])
    random.shuffle(images)

    for img in images:
        if not image_already_used(img):
            return img

    return random.choice(images)

def get_image_url(title, category):
    entity = extract_entity(title)

    queries = [
        entity,
        f"{entity} football",
        f"{entity} sport",
        category
    ]

    for q in queries:
        img = wikipedia_image(q)
        if img and not image_already_used(img):
            return img

    for q in queries:
        img = commons_image(q)
        if img and not image_already_used(img):
            return img

    return random_cover(category)

def rewrite_with_groq(title, summary, category):
    if not GROQ_API_KEY:
        return None

    prompt = f"""
Tulis artikel berita olahraga bahasa Indonesia gaya media profesional.

Syarat:
- Jangan copy paste sumber.
- Jangan menyebut RSS, referensi, atau sumber asli.
- Jangan menulis disclaimer.
- Jangan memakai paragraf template.
- Panjang 700-900 kata.
- SEO-friendly.
- Gunakan gaya berita resmi.
- Jangan mengarang fakta spesifik yang tidak tersedia.
- Jika informasi terbatas, kembangkan konteks umum secara aman.

Judul/topik:
{title}

Ringkasan fakta:
{summary}

Kategori:
{category}
"""

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": "Kamu adalah editor berita olahraga profesional untuk portal Kancah Sports."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.6,
                "max_tokens": 1800
            },
            timeout=60
        )

        if res.status_code != 200:
            print("Groq error:", res.status_code, res.text)
            return None

        return res.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        print("Groq exception:", e)
        return None

def fallback_article(title, summary, category):
    return f"""
{summary}

## Latar Belakang

Kabar terbaru ini menjadi perhatian karena berkaitan dengan perkembangan olahraga yang sedang ramai dibicarakan publik. Dalam dunia sepak bola dan olahraga modern, setiap informasi mengenai tim, pemain, jadwal, maupun hasil pertandingan dapat memengaruhi perhatian suporter dan pembaca.

## Poin Penting

Informasi utama dari kabar ini berpusat pada perkembangan terbaru yang menyangkut {category.lower()}. Topik tersebut menarik karena berhubungan dengan dinamika kompetisi, performa tim, serta perhatian publik terhadap agenda olahraga terkini.

## Dampak Berita

Bagi penggemar, kabar seperti ini menjadi bagian penting untuk memahami situasi terbaru. Perubahan strategi, hasil pertandingan, kondisi pemain, maupun agenda kompetisi sering kali menjadi faktor yang menentukan arah pembahasan olahraga dalam beberapa hari ke depan.

## Penutup

Perkembangan ini menunjukkan bahwa olahraga terus bergerak cepat dan selalu menghadirkan cerita baru. Pembaca dapat terus mengikuti pembaruan berikutnya untuk mengetahui informasi yang lebih lengkap dan terbaru.
""".strip()

def build_article(item, source):
    raw_title = normalize_title(item.get("title", "Berita Olahraga Terbaru"))
    summary = clean_text(item.get("summary", ""))
    source_url = item.get("link", "")

    category = detect_category(raw_title, summary)
    slug = slugify(raw_title)
    excerpt = summary[:220] if summary else f"Update terbaru seputar {raw_title}."
    image_url = get_image_url(raw_title, category)

    content = rewrite_with_groq(raw_title, summary, category)
    if not content:
        content = fallback_article(raw_title, summary, category)

    return {
        "title": raw_title,
        "slug": slug,
        "excerpt": excerpt,
        "content": content,
        "category": category,
        "image_url": image_url,
        "source_name": source["name"],
        "source_url": source_url,
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "seo_title": f"{raw_title} | Kancah Sports",
        "seo_description": excerpt
    }

def upsert_article(article):
    url = f"{SUPABASE_URL}/rest/v1/articles?on_conflict=slug"

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }

    response = requests.post(url, headers=headers, json=article)

    if response.status_code not in [200, 201, 204]:
        print("Upsert error:", response.status_code)
        print(response.text)
        raise Exception("Supabase upsert failed")

    print("Upserted:", article["title"])

def main():
    print("GROQ:", "FOUND" if GROQ_API_KEY else "NOT FOUND")

    for source in RSS_SOURCES:
        feed = feedparser.parse(source["url"])

        print("Source:", source["name"])
        print("Feed title:", feed.feed.get("title"))
        print("Total RSS items:", len(feed.entries))

        for item in feed.entries[:20]:
            published = item.get("published", "")

            try:
                pub_date = parsedate_to_datetime(published)

                if pub_date < datetime.now(timezone.utc) - timedelta(hours=24):
                    print("Skip old article:", item.get("title"))
                    continue

            except Exception as e:
                print("Date parse error:", e)

            article = build_article(item, source)
            upsert_article(article)

if __name__ == "__main__":
    main()