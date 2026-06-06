import os
import re
import html
import requests
import feedparser
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

RSS_SOURCES = [
    {
        "name": "ANTARA Olahraga",
        "url": "https://www.antaranews.com/rss/olahraga.xml",
        "category": "Sports"
    }
]

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:120]

def clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()

def get_image_url(item):
    if item.get("enclosures"):
        enclosure = item.enclosures[0]
        return enclosure.get("href") or enclosure.get("url")

    media_content = item.get("media_content")
    if media_content and len(media_content) > 0:
        return media_content[0].get("url")

    summary = item.get("summary", "")
    match = re.search(r'<img[^>]+src="([^"]+)"', summary)
    if match:
        return match.group(1)

    return None

def build_article(item, source):
    title = clean_text(item.get("title", "Berita Olahraga Terbaru"))
    summary = clean_text(item.get("summary", ""))
    source_url = item.get("link", "")
    slug = slugify(title)

    excerpt = summary[:220] if summary else f"Update terbaru seputar {title}."

    content = f"""
{title}

{summary}

Kabar ini menjadi salah satu perhatian penggemar olahraga, terutama bagi pembaca yang mengikuti perkembangan sepak bola dan kompetisi terkini.

Kancah Sports merangkum informasi ini dengan gaya editorial sendiri agar lebih ringkas, mudah dibaca, dan relevan untuk pembaca Indonesia.

Artikel ini disusun berdasarkan informasi dari sumber referensi yang tercantum. Pembaca dapat mengakses sumber asli untuk membaca detail lengkap dari laporan awal.

Sumber referensi: {source["name"]}
{source_url}
""".strip()

    return {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
        "content": content,
        "category": source["category"],
        "image_url": get_image_url(item),
        "source_name": source["name"],
        "source_url": source_url,
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "seo_title": title,
        "seo_description": excerpt
    }

def insert_article(article):
    url = f"{SUPABASE_URL}/rest/v1/articles"
    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    response = requests.post(url, headers=headers, json=article)

    if response.status_code not in [200, 201, 204]:
        print("Insert error:", response.status_code)
        print(response.text)
        raise Exception("Supabase insert failed")

    print("Inserted:", article["title"])

def main():
    for source in RSS_SOURCES:
        feed = feedparser.parse(source["url"])

        print(f"Source: {source['name']}")
        print("Feed title:", feed.feed.get("title"))
        print(f"Total RSS items: {len(feed.entries)}")

        for item in feed.entries[:5]:
            article = build_article(item, source)
            insert_article(article)

if __name__ == "__main__":
    main()