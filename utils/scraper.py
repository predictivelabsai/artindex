"""Scrape auction data from Allee Galerii and Haus using Playwright."""
import asyncio
import re
from playwright.async_api import async_playwright
from utils.db import init_db, insert_lots

ALLEE_BASE = "https://alleegalerii.ee"
ALLEE_AUCTION_URL = f"{ALLEE_BASE}/kunstioksjon/"
HAUS_URL = "https://haus.ee/?c=toimunud-oksjonid&l=et"

JS_EXTRACT_ALLEE = '''
() => {
  const lots = [];
  document.querySelectorAll('article').forEach(art => {
    const heading = art.querySelector('h3');
    if (!heading) return;
    const text = heading.textContent.trim();
    const match = text.match(/^(.+?)\\s*[\\u201c\\u201d\\u201e"""](.+?)[\\u201c\\u201d"""],?\\s*(\\d{4})\\w*\\.?\\s*(.*)/);
    let author = '', year = null, dims = '';
    if (match) {
      author = match[1].trim();
      year = parseInt(match[3]);
      dims = match[4].trim();
    } else { return; }
    const allText = art.innerText;
    const startMatch = allText.match(/Alghind[:\\s]*(\\d[\\d\\s]*)\\s*\\u20ac/);
    const endMatch = allText.match(/Haamrihind[:\\s]*(\\d[\\d\\s]*)\\s*\\u20ac/);
    let startPrice = 0, endPrice = 0;
    if (startMatch) startPrice = parseInt(startMatch[1].replace(/\\s/g, ''));
    if (endMatch) endPrice = parseInt(endMatch[1].replace(/\\s/g, ''));
    if (startPrice === 0) return;
    let dimension = null;
    const dimMatch = dims.match(/([\\d,\\.]+)\\s*x\\s*([\\d,\\.]+)/);
    if (dimMatch) {
      const w = parseFloat(dimMatch[1].replace(',', '.'));
      const h = parseFloat(dimMatch[2].replace(',', '.'));
      dimension = w * h;
    }
    const catEl = art.querySelector('li');
    const category = catEl ? catEl.textContent.trim() : '';
    lots.push({ author, year, startPrice, endPrice, dimension, category });
  });
  return lots;
}
'''

JS_GET_CATEGORY_LINKS = """
() => {
  const links = [];
  document.querySelectorAll('a').forEach(a => {
    if (a.href.includes('kunstioksjon-kategooria')) {
      links.push({ text: a.textContent.trim(), url: a.href });
    }
  });
  return links;
}
"""

# Haus catalog pages use figcaption with structured elements
JS_EXTRACT_HAUS = """
() => {
  const lots = [];
  document.querySelectorAll('figure').forEach(fig => {
    const cap = fig.querySelector('figcaption');
    if (!cap) return;

    const authorEl = cap.querySelector('em.aut');
    const author = authorEl ? authorEl.textContent.trim() : '';
    if (!author) return;

    const yearEl = cap.querySelector('span.year');
    const year = yearEl ? parseInt(yearEl.textContent.trim()) : null;

    const techEl = cap.querySelector('p.tech');
    let tech = null, dimension = null;
    if (techEl) {
      const pText = techEl.textContent.trim();
      const dotIdx = pText.indexOf('.');
      if (dotIdx > 0) tech = pText.substring(0, dotIdx).trim();
      const dimMatch = pText.match(/([\\d,.]+)\\s*[×x]\\s*([\\d,.]+)/);
      if (dimMatch) {
        const w = parseFloat(dimMatch[1].replace(',', '.'));
        const h = parseFloat(dimMatch[2].replace(',', '.'));
        dimension = w * h;
      }
    }

    const startEl = cap.querySelector('strong.price.r:not(.bid_current):not(.price_final)');
    const endEl = cap.querySelector('strong.price_final');

    let startPrice = 0, endPrice = 0;
    if (startEl) startPrice = parseInt(startEl.textContent.replace(/[^\\d]/g, '')) || 0;
    if (endEl) endPrice = parseInt(endEl.textContent.replace(/[^\\d]/g, '')) || 0;

    lots.push({ author, year, tech, dimension, startPrice, endPrice });
  });
  return lots;
}
"""

JS_GET_HAUS_CATALOGS = """
() => {
  const links = [];
  document.querySelectorAll('a[href*="toimunud-oksjonid"][href*="id="]').forEach(a => {
    if (a.textContent.trim() === 'Vaata kataloogi') {
      // Get the parent article to find the auction title and date
      const article = a.closest('article');
      let title = '', dateStr = '';
      if (article) {
        const h3 = article.querySelector('h3');
        if (h3) title = h3.textContent.trim();
        const time = article.querySelector('time');
        if (time) dateStr = time.textContent.trim();
      }
      links.push({ url: a.href, title, date: dateStr });
    }
  });
  return links;
}
"""


def extract_auction_year(text: str) -> int:
    """Extract year from category/auction name."""
    m = re.search(r"(\d{4})", text)
    return int(m.group(1)) if m else 2024


def decade_from_year(y: int | None) -> int | None:
    return (y // 10) * 10 if y else None


async def scrape_allee(page) -> list[dict]:
    """Scrape all auction lots from Allee Galerii."""
    print("Scraping Allee Galerii...")
    await page.goto(ALLEE_AUCTION_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Accept cookies if dialog present
    try:
        btn = page.locator("button:has-text('Nõustun')")
        if await btn.count() > 0:
            await btn.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass

    # Get auction category URLs
    categories = await page.evaluate(JS_GET_CATEGORY_LINKS)
    seen = set()
    unique_cats = []
    for c in categories:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_cats.append(c)
    print(f"  Found {len(unique_cats)} auction categories")

    all_lots = []
    for cat in unique_cats:
        print(f"  Scraping: {cat['text']}...")
        await page.goto(cat["url"], wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        lots = await page.evaluate(JS_EXTRACT_ALLEE)
        auction_year = extract_auction_year(cat["text"])

        for lot in lots:
            all_lots.append({
                "auction_date": auction_year,
                "author": lot["author"],
                "start_price": lot["startPrice"],
                "end_price": lot["endPrice"] or lot["startPrice"],
                "year": lot["year"],
                "decade": decade_from_year(lot["year"]),
                "tech": None,
                "category": lot.get("category"),
                "dimension": lot["dimension"],
                "auction_provider": "allee",
            })
        print(f"    -> {len(lots)} lots")

    print(f"  Total Allee lots: {len(all_lots)}")
    return all_lots


async def scrape_haus(page) -> list[dict]:
    """Scrape auction data from Haus catalog pages."""
    print("Scraping Haus...")
    await page.goto(HAUS_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Collect catalog links from all pagination pages
    all_catalogs = []
    for page_num in range(1, 5):  # 4 pages of auctions
        if page_num > 1:
            url = f"{HAUS_URL}&_order=date.dsc&ps=25&_s=1&p={page_num}"
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

        catalogs = await page.evaluate(JS_GET_HAUS_CATALOGS)
        all_catalogs.extend(catalogs)
        print(f"  Page {page_num}: found {len(catalogs)} catalogs")

    # Deduplicate by URL
    seen = set()
    unique_catalogs = []
    for c in all_catalogs:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_catalogs.append(c)
    print(f"  Total unique catalogs: {len(unique_catalogs)}")

    all_lots = []
    for cat in unique_catalogs:
        title = cat["title"] or cat["date"]
        print(f"  Scraping: {title[:60]}...")
        await page.goto(cat["url"], wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        lots = await page.evaluate(JS_EXTRACT_HAUS)
        auction_year = extract_auction_year(cat["date"] + " " + cat["title"])

        for lot in lots:
            all_lots.append({
                "auction_date": auction_year,
                "author": lot["author"],
                "start_price": lot["startPrice"],
                "end_price": lot["endPrice"] or lot["startPrice"],
                "year": lot["year"],
                "decade": decade_from_year(lot["year"]),
                "tech": lot.get("tech"),
                "category": None,
                "dimension": lot.get("dimension"),
                "auction_provider": "haus",
            })
        print(f"    -> {len(lots)} lots")

    print(f"  Total Haus lots: {len(all_lots)}")
    return all_lots


async def main():
    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Scrape Allee
        allee_lots = await scrape_allee(page)
        if allee_lots:
            n = insert_lots(allee_lots)
            print(f"Inserted {n} Allee lots into DB")

        # Scrape Haus
        haus_lots = await scrape_haus(page)
        if haus_lots:
            n = insert_lots(haus_lots)
            print(f"Inserted {n} Haus lots into DB")

        await browser.close()

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
