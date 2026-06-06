const Parser = require("rss-parser");

const parser = new Parser();

async function main() {
  const feed = await parser.parseURL(
    "https://www.bola.net/feed/"
  );

  console.log(feed.items.slice(0, 5));
}

main();