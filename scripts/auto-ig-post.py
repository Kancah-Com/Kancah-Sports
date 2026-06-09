import os
import re
import io
import uuid
import html
import json
import time
import requests
import feedparser
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


GROQ_API_KEY = os.environ["GROQ_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

BUCKET = "ig-posts"
POSTED_FILE = "posted_news.json"

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

NEGATIVE_KEYWORDS = [
    "tersinggung", "marah", "kesal", "sindir", "menyindir",
    "kritik", "kritikan", "konflik", "perseteruan", "ribut",
    "cekcok", "drama", "boikot", "serang", "menyerang",
    "panas", "memanas", "provokasi", "kontroversi", "kontroversial",
    "bentrok", "kerusuhan", "ricuh", "dihujat", "hujat"
]

STREAMING_KEYWORDS = [
    "live streaming", "link streaming", "watch live", "siaran langsung",
    "streaming gratis", "cara nonton", "live match", "link nonton",
    "jadwal tv", "tayang dimana", "tayang di mana", "hak siar",
    "vidio", "vision+", "mola tv", "bein sports", "nonton di sini",
    "kick-off pukul", "kick off pukul"
]

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=football+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=soccer+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=football+transfer+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=premier+league+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=champions+league+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=la+liga+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=serie+a+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=bundesliga+when:24h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=timnas+indonesia+when:24h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=liga+1+indonesia+when:24h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persib+when:24h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persija+when:24h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=persebaya+when:24h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=ole+romeny+when:24h&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=kevin+diks+when:24h&hl=id&gl=ID&ceid=ID:id",
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


def get_topic_key(title):
    title = title.lower()
    title = re.sub(r"[^a-zA-Z0-9\s]", " ", title)

    stopwords = [
        "yang", "dan", "dengan", "dalam", "dari", "untuk", "pada",
        "akan", "jadi", "resmi", "terbaru", "kabar", "soal", "usai",
        "the", "and", "for", "with", "from", "after", "before",
        "this", "that", "have", "has", "will", "vs", "are", "was"
    ]

    words = [w for w in title.split() if len(w) > 3 and w not in stopwords]
    return " ".join(words[:7])


def load_posted_news():
    if not os.path.exists(POSTED_FILE):
        return []

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_posted_news(news):
    posted = load_posted_news()

    posted.append({
        "title": news.get("title", ""),
        "link": news.get("link", ""),
        "topic_key": news.get("topic_key", ""),
        "posted_at": datetime.now(timezone.utc).isoformat(),
    })

    posted = posted[-100:]

    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=2)


def is_already_posted(news):
    posted = load_posted_news()

    title = news.get("title", "").lower().strip()
    link = news.get("link", "").strip()
    topic_key = news.get("topic_key", "").strip()

    for item in posted:
        if link and item.get("link") == link:
            return True

        if topic_key and item.get("topic_key") == topic_key:
            return True

        old_title = item.get("title", "").lower().strip()
        if old_title and old_title == title:
            return True

    return False


def detect_main_entity(text):
    text = text.lower()

    entity_map = {
        "persib": "Persib Bandung",
        "persija": "Persija Jakarta",
        "persebaya": "Persebaya Surabaya",
        "arema": "Arema FC",
        "pss sleman": "PSS Sleman",
        "timnas indonesia": "Timnas Indonesia",
        "ole romeny": "Ole Romeny",
        "kevin diks": "Kevin Diks",
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

    for rss in RSS_SOURCES:
        feed = feedparser.parse(rss)

        for item in feed.entries[:30]:
            title = clean_text(item.get("title", ""))
            summary = clean_text(item.get("summary", ""))
            link = item.get("link", "")
            published = item.get("published", "")

            if not title:
                continue

            combined = f"{title} {summary}".lower()

            if any(bad in combined for bad in BAD_KEYWORDS):
                continue

            if any(negative in combined for negative in NEGATIVE_KEYWORDS):
                print("Skip negative/drama news:", title)
                continue

            if any(stream in combined for stream in STREAMING_KEYWORDS):
                print("Skip streaming/copyright-risk news:", title)
                continue

            if not any(good in combined for good in GOOD_KEYWORDS):
                continue

            try:
                pub_date = parsedate_to_datetime(published)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except Exception:
                pub_date = datetime(2000, 1, 1, tzinfo=timezone.utc)

            if pub_date < datetime.now(timezone.utc) - timedelta(hours=24):
                continue

            clean_title = normalize_title(title)

            all_news.append({
                "title": clean_title,
                "summary": summary,
                "link": link,
                "published": published,
                "pub_date": pub_date,
            })

    if not all_news:
        raise Exception("Tidak ada berita bola terbaru 24 jam terakhir")

    all_news = list({news["title"]: news for news in all_news}.values())

    topic_counter = {}

    for news in all_news:
        topic_key = get_topic_key(news["title"])
        news["topic_key"] = topic_key
        topic_counter[topic_key] = topic_counter.get(topic_key, 0) + 1

    for news in all_news:
        age_hours = (datetime.now(timezone.utc) - news["pub_date"]).total_seconds() / 3600
        trend_count = topic_counter.get(news["topic_key"], 1)
        trend_score = trend_count * 100
        recency_score = max(0, 24 - age_hours) * 10

        news["trend_count"] = trend_count
        news["score"] = trend_score + recency_score

    all_news = [news for news in all_news if not is_already_posted(news)]

    if not all_news:
        raise Exception("Semua berita trending terbaru sudah pernah dipost")

    all_news.sort(
        key=lambda x: (x["score"], x["trend_count"], x["pub_date"]),
        reverse=True,
    )

    print("Total berita:", len(all_news))
    print("Terpilih:", all_news[0]["title"])
    print("Published:", all_news[0]["published"])
    print("Topic:", all_news[0]["topic_key"])
    print("Trend count:", all_news[0]["trend_count"])
    print("Score:", all_news[0]["score"])

    return all_news[0]


def fallback_data(news):
    title = normalize_title(news.get("title", ""))
    main_entity = detect_main_entity(f'{title} {news.get("summary", "")}')

    words = title.split()
    base_headline = " ".join(words[:16])

    if len(base_headline.split()) < 10:
        headline = f"{base_headline} Jadi Perhatian Baru Sepak Bola Hari Ini"
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
        "main_person": "",
        "main_team": main_entity,
        "image_context": "football_news",
        "image_query": f"{main_entity} football match",
        "must_include": [main_entity],
        "avoid": ["logo", "game", "fifa card", "pes", "fc 25", "wallpaper", "poster"],
        "caption": (
            f"{headline}\n\n"
            f"Kabar ini menjadi salah satu perkembangan terbaru di sepak bola yang menarik untuk diikuti. "
            f"Situasi tersebut berkaitan langsung dengan dinamika tim dan keputusan yang bisa berdampak pada langkah berikutnya.\n\n"
            f"Update lanjutan akan menjadi penentu arah kabar ini dalam beberapa waktu ke depan.\n\n"
            f"_\n#KancahSports #FuelTheGame #KancahFootball"
        ),
        "hashtags": ["#KancahSports", "#FuelTheGame", "#KancahFootball"],
    }


def groq_generate(news):
    main_entity = detect_main_entity(f'{news["title"]} {news["summary"]}')

    prompt = f"""
Buat data JSON untuk konten Instagram Kancah Sports.

Pilih template:
- breaking: untuk berita umum, transfer, rumor, update pemain, kabar klub
- quote: jika berita berisi pernyataan/komentar seseorang
- fulltime: jika berita jelas berisi hasil akhir pertandingan dengan skor

Rules headline:
- Gunakan bahasa Indonesia yang natural, tajam, dan cocok untuk media bola.
- Headline wajib maksimal 14 kata.
- Headline harus tetap informatif dan tidak terlalu panjang.
- Headline ideal tampil maksimal 3 baris di poster.
- Jangan ALL CAPS.
- Jangan pakai tanda kutip dua di dalam value JSON.
- Jangan buat headline list/rangkuman seperti A, B, dan C.
- Breaking News tetap hanya headline, tanpa subheadline.
- Headline harus fokus SATU berita utama saja.
- Hindari kalimat provokatif yang menyinggung klub/suporter.
- Jangan gunakan kata seperti tersinggung, marah, panas, ribut, serang, drama.

Rules caption:
- Caption ditulis seperti caption media bola Indonesia, bukan gaya AI.
- Caption harus informatif, rapi, dan mengalir seperti berita singkat.
- Caption 3-5 paragraf pendek.
- Paragraf pertama langsung masuk ke inti kabar.
- Paragraf kedua menjelaskan konteks.
- Paragraf berikutnya menjelaskan dampak/kemungkinan lanjutan.
- Jangan pakai emoji berlebihan.
- Jangan pakai pertanyaan retoris di akhir.
- Jangan pakai CTA berlebihan.
- Jangan menulis atau mempromosikan link live streaming.
- Akhiri caption dengan format:
_
#KancahSports #FuelTheGame #KancahFootball

Rules gambar:
- Ambil entity utama dari berita.
- Jika berita tentang pemain, isi main_person dengan nama pemain.
- Jika berita tentang klub/tim, isi main_team dengan nama klub/tim.
- Jika berita tentang tim nasional, isi main_team dengan nama tim nasional.
- Jika berita tentang kompetisi, isi competition.
- image_context isi konteks singkat seperti transfer_news, contract_news, national_team, match_result, injury_news, club_news, coach_news.
- image_query wajib spesifik berdasarkan konteks berita.
- Jangan pakai image_query umum seperti football atau soccer.
- must_include wajib berisi entity yang harus muncul di gambar, misalnya nama pemain dan/atau nama klub/tim.
- avoid isi hal yang tidak relevan seperti logo, game, fifa card, pes, fc 25, wallpaper, poster, live streaming.
- Jangan hardcode satu pemain atau satu klub. Sesuaikan dengan berita yang diberikan.

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
  "main_person": "",
  "main_team": "{main_entity}",
  "image_context": "football_news",
  "image_query": "{main_entity} football match",
  "must_include": ["{main_entity}"],
  "avoid": ["logo", "game", "fifa card", "pes", "fc 25", "wallpaper", "poster", "live streaming"],
  "caption": "...",
  "hashtags": ["#KancahSports", "#FuelTheGame", "#KancahFootball"]
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
                {"role": "system", "content": "Balas hanya JSON valid. Jangan markdown."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.45,
            "max_tokens": 1000,
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

    fallback = fallback_data(news)

    if not data.get("headline"):
        data["headline"] = fallback["headline"]

    headline_words = data["headline"].split()
    if len(headline_words) > 14:
        data["headline"] = " ".join(headline_words[:14])

    if len(data["headline"].split()) < 8:
        data["headline"] = f'{data["headline"]} Jadi Sorotan Sepak Bola Hari Ini'

    if not data.get("main_person"):
        data["main_person"] = ""

    if not data.get("main_team"):
        data["main_team"] = main_entity

    if not data.get("competition"):
        data["competition"] = ""

    if not data.get("image_context"):
        data["image_context"] = "football_news"

    if not data.get("image_query"):
        if data.get("main_person") and data.get("main_team"):
            data["image_query"] = f'{data["main_person"]} {data["main_team"]} football match'
        else:
            data["image_query"] = f"{main_entity} football match"

    if not data.get("must_include"):
        must = []
        if data.get("main_person"):
            must.append(data["main_person"])
        if data.get("main_team"):
            must.append(data["main_team"])
        data["must_include"] = must or [main_entity]

    if not data.get("avoid"):
        data["avoid"] = ["logo", "game", "fifa card", "pes", "fc 25", "wallpaper", "poster", "live streaming"]

    if not data.get("caption"):
        data["caption"] = fallback["caption"]

    if "#KancahSports" not in data["caption"]:
        data["caption"] = data["caption"].rstrip() + "\n\n_\n#KancahSports #FuelTheGame #KancahFootball"

    if not data.get("hashtags"):
        data["hashtags"] = ["#KancahSports", "#FuelTheGame", "#KancahFootball"]

    return data


def build_smart_image_queries(data):
    headline = data.get("headline", "")
    image_query = data.get("image_query", "")
    main_person = data.get("main_person", "")
    main_team = data.get("main_team", "")
    competition = data.get("competition", "")
    context = data.get("image_context", "")

    queries = []

    if main_person and main_team:
        queries.extend([
            f"{main_person} {main_team} match",
            f"{main_person} {main_team} action",
            f"{main_person} {main_team} football",
            f"{main_person} {main_team} player",
        ])

    if main_person and competition:
        queries.extend([
            f"{main_person} {competition}",
            f"{main_person} {competition} match",
            f"{main_person} {competition} football",
        ])

    if main_person:
        queries.extend([
            f"{main_person} football match",
            f"{main_person} football player",
            f"{main_person} action photo",
        ])

    if main_team and competition:
        queries.extend([
            f"{main_team} {competition} match",
            f"{main_team} {competition} players",
            f"{main_team} {competition} football",
        ])

    if main_team:
        queries.extend([
            f"{main_team} football match",
            f"{main_team} players match",
            f"{main_team} action football",
        ])

    if image_query:
        queries.append(image_query)

    if headline:
        queries.append(headline)

    if context:
        if main_person:
            queries.append(f"{main_person} {context}")
        if main_team:
            queries.append(f"{main_team} {context}")

    queries.extend([
        "football match players",
        "football stadium players",
    ])

    seen = set()
    return [q for q in queries if q and not (q in seen or seen.add(q))]


def serper_image_search(query, must_include=None, avoid=None):
    if not SERPER_API_KEY:
        print("SERPER_API_KEY kosong, skip Serper image search")
        return None

    must_include = [x.lower() for x in (must_include or []) if x]
    avoid = [x.lower() for x in (avoid or []) if x]

    hard_bad = [
        "logo", "icon", "fifa", "fc 25", "fc25", "pes",
        "efootball", "game", "wallpaper", "poster",
        "transfermarkt", "sofascore", "lineup", "kit", "jersey store",
        "live streaming", "streaming", "watch live", "vidio", "youtube", "tiktok",

        # WATERMARK / STOCK PHOTO SOURCES
        "gettyimages", "getty images", "getty",
        "shutterstock",
        "alamy",
        "dreamstime",
        "depositphotos",
        "123rf",
        "istock", "istockphoto",
        "freepik",
        "vectorstock",
        "alamyimages",

        # ANTARA FOTO sering ada watermark besar di tengah
        "antarafoto",
        "img.antarafoto.com",
    ]

    trusted_sources = [
        "reuters",
        "apnews",
        "ap news",
        "bbc",
        "espn",
        "skysports",
        "sky sports",
        "goal",
        "fifa.com",
        "the-afc.com",
        "uefa.com",
        "premierleague.com",
        "laliga.com",
        "seriea.com",
        "bundesliga.com",
        "pssi.org",
        "persib.co.id",
        "persija.id",
        "kompas",
        "detik",
        "bola.com",
        "tempo",
    ]

    try:
        r = requests.post(
            "https://google.serper.dev/images",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 20},
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
            width = item.get("imageWidth") or 0
            height = item.get("imageHeight") or 0

            haystack = f"{url} {title} {source}".lower()

            if not url:
                continue

            # langsung skip sumber yang rawan watermark / copyright-risk / thumbnail video
            if any(bad in haystack for bad in hard_bad):
                print("SKIP WATERMARK/BAD SOURCE:", title, "|", url)
                continue

            score = 0

            for bad in avoid:
                if bad and bad in haystack:
                    score -= 100

            for m in must_include:
                words = [w for w in m.split() if len(w) > 2]
                matched = sum(1 for w in words if w in haystack)
                score += matched * 25

            for word in query.lower().split():
                if len(word) > 3 and word in haystack:
                    score += 8

            action_words = [
                "match", "action", "player", "training",
                "goal", "celebration", "football", "soccer"
            ]
            if any(w in haystack for w in action_words):
                score += 20

            if any(s in haystack for s in trusted_sources):
                score += 40

            # hindari sosmed crawler karena sering gagal dibuka
            if "lookaside.instagram" in haystack or "lookaside.fbsbx" in haystack:
                score -= 80

            # hindari foto kecil
            if width < 500 or height < 400:
                score -= 50

            if width >= 700 and height >= 700:
                score += 15

            if width >= 1000 or height >= 1000:
                score += 10

            if height > width:
                score += 5

            print("IMG CANDIDATE:", score, "|", title, "|", url)

            if score > best_score:
                best_score = score
                best = url

        if best and best_score > 0:
            print("BEST IMAGE:", best)
            print("BEST SCORE:", best_score)
            return best

        print("No good Serper image. Best score:", best_score)

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
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
            allow_redirects=True,
        )

        if r.status_code != 200:
            print("Image download failed:", r.status_code, url)
            return None

        content_type = r.headers.get("Content-Type", "").lower()

        if "image" not in content_type and len(r.content) < 5000:
            print("Not valid image response:", content_type, url)
            return None

        img = Image.open(io.BytesIO(r.content)).convert("RGBA")

        if img.width < 200 or img.height < 150:
            print("Image too small:", img.width, img.height, url)
            return None

        return img

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
        return r.url

    except Exception as e:
        print("Resolve Google News URL error:", e)
        return url


def extract_og_image(article_url):
    if not article_url:
        return None

    try:
        real_url = resolve_google_news_url(article_url)
        print("Resolved article URL:", real_url)

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


def get_background_image(keyword, source_link=None, must_include=None, avoid=None, data=None):
    must_include = must_include or []
    avoid = avoid or []

    print("Image query:", keyword)
    print("Source link:", source_link)
    print("Must include:", must_include)
    print("Avoid:", avoid)

    search_queries = build_smart_image_queries(data or {
        "headline": keyword,
        "image_query": keyword,
        "main_person": "",
        "main_team": must_include[0] if must_include else "",
        "competition": "",
        "image_context": "football_news",
    })

    print("SMART QUERIES:", search_queries)

    for q in search_queries:
        print("Try Serper smart:", q)

        serper_url = serper_image_search(
            q,
            must_include=must_include,
           avoid=avoid + [
                     "logo", "icon", "fifa card", "pes", "fc 25",
                     "game", "wallpaper", "poster", "live streaming",
                     "getty", "gettyimages", "alamy", "shutterstock",
                     "dreamstime", "depositphotos", "istock", "freepik",
                     "antarafoto", "img.antarafoto.com"
                    ],
        )

        img = download_image(serper_url)
        if img:
            print("Using Serper image")
            return img

    og_url = extract_og_image(source_link)
    img = download_image(og_url)
    if img:
        print("Using OG image")
        return img

    for q in search_queries:
        print("Try Wikipedia:", q)
        img_url = wikipedia_image(q)
        img = download_image(img_url)
        if img:
            print("Using Wikipedia image")
            return img

    for q in search_queries:
        print("Try Commons:", q)
        img_url = commons_image(q)
        img = download_image(img_url)
        if img:
            print("Using Commons image")
            return img

    print("NO IMAGE FOUND")
    return None


def get_team_logo(team_name):
    name = (team_name or "").lower().strip()

    for key, code in COUNTRY_CODES.items():
        if key in name:
            return download_image(f"https://flagcdn.com/w640/{code}.png")

    img = download_image(wikipedia_image(f"{team_name} football club logo"))
    if img:
        return img

    img = download_image(commons_image(f"{team_name} logo football"))
    if img:
        return img

    return None


def make_gradient_fallback(width=1080, height=1350):
    bg = Image.new("RGBA", (width, height), (15, 15, 15, 255))
    draw = ImageDraw.Draw(bg)

    for y in range(height):
        shade = int(18 + (y / height) * 45)
        draw.line((0, y, width, y), fill=(shade, shade, shade, 255))

    for i in range(0, width, 120):
        draw.line((i, 0, i - 280, height), fill=(45, 45, 45, 45), width=2)

    return bg


def enhance_sports_image(img):
    img = img.convert("RGBA")
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(1.35)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=220, threshold=2))
    return img


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


def limit_text_to_lines(draw, text, font, max_width, max_lines):
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

        if len(lines) == max_lines:
            break

    if len(lines) < max_lines and line:
        lines.append(line)

    lines = lines[:max_lines]

    used_words = " ".join(lines).replace("...", "").split()
    original_words = str(text).strip().split()

    if len(used_words) < len(original_words) and lines:
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "...", font=font)[2] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last + "..."

    return lines


def fit_multiline(
    draw,
    text,
    max_width,
    max_height,
    start_size,
    min_size,
    weight="bold",
    uppercase=False,
    max_lines=None,
):
    text = str(text)
    if uppercase:
        text = text.upper()

    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, weight)
        lines = wrap_text(draw, text, font, max_width)

        if max_lines and len(lines) > max_lines:
            continue

        line_height = int(size * 0.92)
        total = len(lines) * line_height

        if total <= max_height:
            return font, lines, line_height

    font = get_font(min_size, weight)

    if max_lines:
        lines = limit_text_to_lines(draw, text, font, max_width, max_lines)
    else:
        lines = wrap_text(draw, text, font, max_width)

    return font, lines, int(min_size * 0.92)


def draw_left_multiline(
    draw,
    text,
    x,
    y,
    max_width,
    max_height,
    start_size=76,
    min_size=42,
    fill=WHITE,
    weight="bold",
    max_lines=None,
):
    font, lines, line_height = fit_multiline(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        weight=weight,
        uppercase=False,
        max_lines=max_lines,
    )

    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        cy += line_height


def draw_centered(
    draw,
    text,
    x,
    y,
    max_width,
    max_height,
    start_size=78,
    min_size=42,
    fill=WHITE,
    weight="bold",
    max_lines=None,
):
    font, lines, line_height = fit_multiline(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        weight=weight,
        uppercase=False,
        max_lines=max_lines,
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
        or data.get("headline")
        or "football match players"
    )

    print("FINAL BG KEYWORD:", bg_keyword)

    bg_img = get_background_image(
        bg_keyword,
        data.get("source_link"),
        must_include=data.get("must_include", []),
        avoid=data.get("avoid", []),
        data=data,
    )

    if bg_img is None:
        print("Fallback gradient background")
        bg = make_gradient_fallback(W, H)
    else:
        print("Background image loaded:", bg_img.width, bg_img.height)
        bg = cover_crop(bg_img, W, H)
        bg = enhance_sports_image(bg)

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
            max_lines=4,
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
            max_lines=2,
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
            max_lines=2,
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
            max_lines=2,
        )

    else:
        headline = data.get("headline", "Update terbaru")

        draw_left_multiline(
            draw,
            headline,
            x=58,
            y=1035,
            max_width=970,
            max_height=210,
            start_size=56,
            min_size=32,
            fill=WHITE,
            weight="bold",
            max_lines=3,
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
    print("Main person:", data.get("main_person", ""))
    print("Main team:", data.get("main_team", ""))
    print("Competition:", data.get("competition", ""))
    print("Image context:", data.get("image_context", ""))
    print("Image query:", data.get("image_query", ""))
    print("Must include:", data.get("must_include", []))
    print("Caption:", data.get("caption", ""))

    data["source_link"] = news.get("link", "")

    poster = generate_poster(data)
    image_url = upload_to_supabase(poster)

    caption = data.get("caption", news["summary"])

    publish_instagram(image_url, caption)

    save_posted_news(news)


if __name__ == "__main__":
    main()