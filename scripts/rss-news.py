import os
import re
import html
import requests
import feedparser
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

RSS_SOURCES = [
    {
        "name": "ANTARA Olahraga",
        "url": "https://www.antaranews.com/rss/olahraga.xml",
        "category": "Sports"
    }
]

FALLBACK_IMAGES = {
    "Football": "https://images.unsplash.com/photo-1579952363873-27f3bade9f55?q=90&w=1600&auto=format&fit=crop",
    "Futsal": "https://images.unsplash.com/photo-1556056504-5c7696c4c28d?q=90&w=1600&auto=format&fit=crop",
    "Basketball": "https://images.unsplash.com/photo-1546519638-68e109498ffc?q=90&w=1600&auto=format&fit=crop",
    "Badminton": "https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?q=90&w=1600&auto=format&fit=crop",
    "F1": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?q=90&w=1600&auto=format&fit=crop",
    "Sports": "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?q=90&w=1600&auto=format&fit=crop"
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

def detect_category(title, summary):
    text = f"{title} {summary}".lower()

    if any(k in text for k in ["persib", "persija", "timnas", "bola", "sepak bola", "liga", "fifa", "afc"]):
        return "Football"
    if any(k in text for k in ["futsal"]):
        return "Futsal"
    if any(k in text for k in ["basket", "nba"]):
        return "Basketball"
    if any(k in text for k in ["badminton", "bulu tangkis"]):
        return "Badminton"
    if any(k in text for k in ["f1", "formula 1", "motogp"]):
        return "F1"

    return "Sports"

def extract_entity(title):
    entities = [
        "Ole Romeny", "Persib", "Persija", "Arema", "Persebaya",
        "Timnas Indonesia", "PSSI", "Erick Thohir", "AFC",
        "Liverpool", "Manchester United", "Real Madrid", "Barcelona",
        "Futsal Indonesia", "SEA Games", "MotoGP", "Formula 1"
    ]

    lower_title = title.lower()

    for entity in entities:
        if entity.lower() in lower_title:
            return entity

    words = re.findall(r"[A-Za-z0-9]+", title)
    stop = {
        "dan", "yang", "dari", "dalam", "untuk", "dengan",
        "harga", "jadwal", "profil", "mengenal", "cara",
        "aturan", "berikut", "simak", "ini"
    }

    clean_words = [w for w in words if len(w) > 3 and w.lower() not in stop]
    return " ".join(clean_words[:4]) or title

def commons_image(query):
    try:
        headers = {
            "User-Agent": "KancahSportsBot/1.0 (kancahcreative@gmail.com)"
        }

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json"
        }

        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params,
            headers=headers,
            timeout=15
        )

        if r.status_code != 200:
            return None

        data = r.json()
        pages = data.get("query", {}).get("pages", {})

        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            url = info.get("url")
            width = info.get("width", 0)
            mime = info.get("mime", "")

            if url and width >= 700 and mime.startswith("image/"):
                return url

    except Exception as e:
        print("Commons image error:", e)

    return None

def get_image_url(title, category):
    entity = extract_entity(title)

    queries = [
        f"{entity} football",
        f"{entity} sport",
        entity,
        category
    ]

    for q in queries:
        img = commons_image(q)
        if img:
            return img

    return FALLBACK_IMAGES.get(category, FALLBACK_IMAGES["Sports"])

def rewrite_with_groq(title, summary, category):
    if not GROQ_API_KEY:
        return None

    prompt = f"""
Tulis artikel berita olahraga bahasa Indonesia gaya media profesional.

Syarat:
- Jangan copy paste sumber.
- Jangan menyebut "berdasarkan RSS", "referensi", atau "Kancah Sports merangkum".
- Panjang 700-900 kata.
- Gaya berita resmi, natural, SEO-friendly.
- Struktur jelas dengan subjudul.
- Jangan mengarang fakta spesifik yang tidak ada.
- Gunakan informasi yang tersedia saja.
- Jika data terbatas, kembangkan konteks umum secara aman.
- Topik: {title}
- Ringkasan fakta: {summary}
- Kategori: {category}

Format:
Paragraf pembuka berita.
Subjudul 1.
Isi.
Subjudul 2.
Isi.
Subjudul 3.
Isi.
Penutup.
"""

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
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
                "temperature": 0.7,
                "max_tokens": 1400
            },
            timeout=40
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

## Fokus Utama

Kabar ini menjadi perhatian karena berkaitan dengan perkembangan terbaru di dunia {category.lower()}. Informasi tersebut menarik untuk diikuti, terutama bagi pembaca yang ingin mengetahui update olahraga nasional maupun internasional secara ringkas dan mudah dipahami.

## Konteks Berita

Perkembangan olahraga tidak hanya ditentukan oleh hasil pertandingan, tetapi juga oleh jadwal, kesiapan atlet, dinamika tim, dan agenda kompetisi. Karena itu, setiap kabar terbaru dapat memberi gambaran mengenai arah persaingan dan situasi terkini di cabang olahraga terkait.

## Dampak untuk Penggemar

Bagi penggemar, informasi seperti ini membantu memahami kondisi terbaru sebelum pertandingan, turnamen, atau agenda olahraga berlangsung. Perubahan jadwal, harga tiket, profil atlet, dan kabar kompetisi sering kali menjadi faktor penting bagi publik.

## Kesimpulan

Kabar ini menambah daftar perkembangan penting dalam dunia olahraga. Pembaca dapat terus mengikuti update berikutnya untuk mengetahui perubahan terbaru, jadwal lanjutan, dan informasi resmi yang berkaitan dengan topik ini.
""".strip()

def build_article(item, source):
    original_title = clean_text(item.get("title", "Berita Olahraga Terbaru"))
    summary = clean_text(item.get("summary", ""))
    source_url = item.get("link", "")

    category = detect_category(original_title, summary)
    title = original_title
    slug = slugify(title)
    excerpt = summary[:220] if summary else f"Update terbaru seputar {title}."
    image_url = get_image_url(title, category)

    ai_content = rewrite_with_groq(title, summary, category)
    content = ai_content if ai_content else fallback_article(title, summary, category)

    return {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
        "content": content,
        "category": category,
        "image_url": image_url,
        "source_name": source["name"],
        "source_url": source_url,
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "seo_title": f"{title} | Kancah Sports",
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
    for source in RSS_SOURCES:
        feed = feedparser.parse(source["url"])

        print("Source:", source["name"])
        print("Feed title:", feed.feed.get("title"))
        print("Total RSS items:", len(feed.entries))

        for item in feed.entries[:5]:
            article = build_article(item, source)
            upsert_article(article)

if __name__ == "__main__":
    main()