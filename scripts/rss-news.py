import os, re, html, requests, feedparser
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
    return re.sub(r"-+", "-", text).strip("-")[:120]

def clean_text(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()

def extract_keywords(title):
    stop = {"dan","yang","di","ke","dari","ini","itu","cara","aturan","jadwal","harga","profil","mengenal"}
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    words = [w for w in words if len(w) > 2 and w not in stop]
    return " ".join(words[:5]) or title

def commons_image(query):
    try:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json"
        }
        r = requests.get("https://commons.wikimedia.org/w/api.php", params=params, timeout=15)
        pages = r.json().get("query", {}).get("pages", {})
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

def rss_image(item):
    if item.get("enclosures"):
        img = item.enclosures[0].get("href") or item.enclosures[0].get("url")
        if img and "logo" not in img.lower():
            return img

    media = item.get("media_content")
    if media and len(media) > 0:
        img = media[0].get("url")
        if img and "logo" not in img.lower():
            return img

    summary = item.get("summary", "")
    match = re.search(r'<img[^>]+src="([^"]+)"', summary)
    if match:
        return match.group(1)

    return None

def get_image_url(title, item):
    query = extract_keywords(title)

    img = commons_image(query)
    if img:
        return img

    img = rss_image(item)
    if img:
        return img

    return "https://images.unsplash.com/photo-1579952363873-27f3bade9f55?q=90&w=1600&auto=format&fit=crop"

def make_title(title):
    title = clean_text(title)
    if len(title) <= 70:
        return title
    return title[:67].rstrip() + "..."

def build_content(title, summary, source_name):
    summary = summary.rstrip(".")
    return f"""
{summary}.

Kancah Sports melihat kabar ini sebagai salah satu informasi penting dalam perkembangan olahraga nasional maupun internasional. Isu tersebut menarik perhatian karena berkaitan dengan dinamika kompetisi, atlet, klub, dan agenda olahraga yang terus bergerak cepat.

Dalam konteks olahraga modern, informasi seperti ini tidak hanya penting bagi penggemar, tetapi juga bagi pelaku industri, komunitas, dan pembaca yang mengikuti perkembangan cabang olahraga terkait. Setiap kabar terbaru dapat memberi gambaran mengenai arah persaingan, kesiapan tim, maupun peluang prestasi di masa mendatang.

Berita ini juga menunjukkan bahwa olahraga terus menjadi ruang yang dinamis. Perubahan jadwal, hasil pertandingan, profil atlet, hingga perkembangan kompetisi selalu memiliki dampak terhadap antusiasme publik.

Kancah Sports merangkum informasi ini dalam format yang lebih ringkas, jelas, dan mudah dibaca. Fokus utama artikel ini adalah membantu pembaca memahami inti kabar tanpa kehilangan konteks penting yang melatarbelakanginya.

Ke depan, Kancah Sports akan terus memantau perkembangan terbaru seputar sepak bola, olahraga nasional, dan berbagai cabang olahraga populer lainnya.
""".strip()

def build_article(item, source):
    raw_title = clean_text(item.get("title", "Berita Olahraga Terbaru"))
    summary = clean_text(item.get("summary", ""))
    source_url = item.get("link", "")

    title = make_title(raw_title)
    slug = slugify(title)
    excerpt = summary[:220] if summary else f"Update terbaru seputar {title}."
    image_url = get_image_url(title, item)

    return {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
        "content": build_content(title, summary, source["name"]),
        "category": source["category"],
        "image_url": image_url,
        "source_name": source["name"],
        "source_url": source_url,
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "seo_title": f"{title} - Kancah Sports",
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

    res = requests.post(url, headers=headers, json=article)

    if res.status_code not in [200, 201, 204]:
        if "duplicate" in res.text.lower():
            print("Duplicate skip:", article["title"])
            return
        print("Insert error:", res.status_code, res.text)
        raise Exception("Supabase insert failed")

    print("Inserted:", article["title"])

def main():
    for source in RSS_SOURCES:
        feed = feedparser.parse(source["url"])

        print("Source:", source["name"])
        print("Feed title:", feed.feed.get("title"))
        print("Total RSS items:", len(feed.entries))

        for item in feed.entries[:5]:
            article = build_article(item, source)
            insert_article(article)

if __name__ == "__main__":
    main()