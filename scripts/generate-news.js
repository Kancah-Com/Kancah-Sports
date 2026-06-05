const API_KEY = process.env.API_FOOTBALL_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SECRET_KEY = process.env.SUPABASE_SECRET_KEY;

const LEAGUE_ID = 274;
const SEASON = 2025;

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

async function apiFootball(path) {
  const res = await fetch(`https://v3.football.api-sports.io/${path}`, {
    headers: {
      "x-apisports-key": API_KEY
    }
  });

  if (!res.ok) throw new Error(`API Football error: ${res.status}`);
  return res.json();
}

async function insertArticle(article) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/articles`, {
    method: "POST",
    headers: {
      "apikey": SUPABASE_SECRET_KEY,
      "Authorization": `Bearer ${SUPABASE_SECRET_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "resolution=merge-duplicates"
    },
    body: JSON.stringify(article)
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supabase insert error: ${text}`);
  }
}

function makeArticle(match) {
  const fixtureId = String(match.fixture.id);
  const home = match.teams.home.name;
  const away = match.teams.away.name;
  const homeGoals = match.goals.home;
  const awayGoals = match.goals.away;
  const league = match.league.name;

  const isFinished = match.fixture.status.short === "FT";

  let title;
  let excerpt;
  let content;

  if (isFinished) {
    title = `${home} vs ${away}: Hasil Akhir ${homeGoals}-${awayGoals} di ${league}`;

    excerpt = `${home} dan ${away} telah menyelesaikan pertandingan ${league} dengan skor akhir ${homeGoals}-${awayGoals}.`;

    content = `${home} dan ${away} bertemu dalam lanjutan ${league} musim 2025/2026.

Pertandingan berakhir dengan skor ${homeGoals}-${awayGoals}. Hasil ini menjadi salah satu catatan penting dalam perjalanan kedua tim di kompetisi musim ini.

${home} tampil sebagai tuan rumah dalam pertandingan ini, sementara ${away} datang dengan misi mencuri poin. Jalannya pertandingan menjadi perhatian para pendukung, terutama karena hasil ini dapat memengaruhi posisi kedua tim di klasemen.

Kancah Sports akan terus memantau perkembangan hasil pertandingan, jadwal terbaru, klasemen, dan kabar penting lainnya dari ${league}.`;
  } else {
    const date = new Date(match.fixture.date).toLocaleDateString("id-ID", {
      day: "2-digit",
      month: "long",
      year: "numeric"
    });

    title = `Jadwal ${home} vs ${away} di ${league}`;

    excerpt = `${home} akan menghadapi ${away} pada lanjutan ${league} musim 2025/2026.`;

    content = `${home} dijadwalkan menghadapi ${away} pada ${date} dalam lanjutan ${league} musim 2025/2026.

Pertandingan ini menjadi salah satu laga yang menarik untuk diikuti karena kedua tim sama-sama membutuhkan hasil positif untuk menjaga posisi mereka di kompetisi.

Duel ${home} vs ${away} diprediksi berjalan ketat. Kancah Sports akan terus memperbarui informasi jadwal, hasil pertandingan, dan klasemen terbaru setelah laga berlangsung.`;
  }

  const slug = slugify(title);

  return {
    title,
    slug,
    excerpt,
    content,
    category: "Liga 1",
    image_url: match.league.logo,
    source_id: fixtureId,
    match_id: fixtureId,
    league_id: LEAGUE_ID,
    season: SEASON,
    status: "published",
    published_at: new Date().toISOString(),
    seo_title: title,
    seo_description: excerpt
  };
}

async function main() {
  if (!API_KEY || !SUPABASE_URL || !SUPABASE_SECRET_KEY) {
    throw new Error("Environment variable belum lengkap.");
  }

  const allFixtures = await apiFootball(`fixtures?league=${LEAGUE_ID}&season=${SEASON}`);

console.log("API errors:", allFixtures.errors);
console.log("API results:", allFixtures.results);

const now = new Date();

const matches = (allFixtures.response || [])
  .filter(match => match.fixture && match.fixture.date)
  .sort((a, b) => {
    const da = Math.abs(new Date(a.fixture.date) - now);
    const db = Math.abs(new Date(b.fixture.date) - now);
    return da - db;
  })
  .slice(0, 10);

  console.log(`Total match ditemukan: ${matches.length}`);

  for (const match of matches) {
    const article = makeArticle(match);

    try {
      await insertArticle(article);
      console.log(`Inserted: ${article.title}`);
    } catch (err) {
      console.log(`Skip/Error: ${article.title}`);
      console.log(err.message);
    }
  }
}

main();