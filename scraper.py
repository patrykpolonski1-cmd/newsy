import json
import os
import re
from bs4 import BeautifulSoup
import feedparser
from playwright.sync_api import sync_playwright
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
HISTORY_FILE = "history.json"


def load_history():
  if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
      return json.load(f)
  return []


def save_history(history):
  with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history[-3000:], f, ensure_ascii=False, indent=2)


def send_discord(source, title, url):
  if not WEBHOOK_URL:
    print(f"[TEST] {source}: {title} -> {url}")
    return
  payload = {"content": f"📡 **{source}**\n**{title}**\n{url}"}
  requests.post(WEBHOOK_URL, json=payload, timeout=10)


def accept_cookies(page):
  button_texts = [
      "Alle akzeptieren",
      "Akzeptieren und weiter",
      "Zustimmen und weiter",
      "Einverstanden",
      "Akzeptieren",
      "Zustimmen",
      "Accept all",
      "Sprejmi vse",
      "Accetta tutto",
  ]
  for frame in [page] + page.frames:
    for text in button_texts:
      try:
        btn = frame.get_by_role(
            "button", name=re.compile(text, re.IGNORECASE)
        ).first
        if btn.is_visible(timeout=400):
          btn.click(timeout=1000)
          page.wait_for_timeout(1500)
          return
      except Exception:
        pass


def fetch_html_playwright(page, url, wait_ms=3500):
  try:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    accept_cookies(page)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(wait_ms)
    return BeautifulSoup(page.content(), "html.parser")
  except Exception as e:
    print(f"❌ Błąd Playwright dla {url}: {e}")
    return None


def check_yle():
  articles = []
  try:
    feed = feedparser.parse(
        "https://feeds.yle.fi/uutiset/v1/recent.rss?concepts=18-206418"
    )
    for entry in feed.entries:
      if entry.get("title") and entry.get("link"):
        articles.append(
            ("Yle.fi (FIN)", entry.title.strip(), entry.link.strip())
        )
  except Exception as e:
    print(f"❌ Yle błąd: {e}")
  print(f"✅ [Yle.fi] Znaleziono: {len(articles)}")
  return articles


def check_blick(page):
  soup = fetch_html_playwright(
      page, "https://www.blick.ch/sport/wintersport/skispringen"
  )
  articles = []
  if soup:
    for a in soup.find_all(
        "a",
        href=re.compile(r"/sport/wintersport/skispringen/[^/]+/[a-z0-9]+$"),
    ):
      href = a["href"]
      url = href if href.startswith("http") else "https://www.blick.ch" + href
      title = a.get_text(" ", strip=True)
      if len(title) < 15:
        title = a.get("title") or a.get("aria-label") or ""
      if len(title) < 15:
        parent = a.find_parent(["article", "div", "li"])
        if parent:
          heading = parent.find(["h1", "h2", "h3", "h4"])
          if heading:
            title = heading.get_text(" ", strip=True)
      if len(title) > 15:
        articles.append(("Blick (SUI)", title, url))
  print(f"✅ [Blick.ch] Znaleziono: {len(articles)}")
  return articles


def check_sloski(page):
  soup = fetch_html_playwright(page, "https://www.sloski.si/")
  articles = []
  if soup:
    for a in soup.find_all("a", href=True):
      href = a["href"]
      title = a.get_text(" ", strip=True)
      if (
          "sloski.si/" in href
          and len(title) > 22
          and not any(
              x in href
              for x in [
                  "/wp-",
                  "/category/",
                  "/tag/",
                  "/kontakt",
                  "/o-nas",
                  "/panoge",
              ]
          )
      ):
        articles.append(("Sloski.si (SLO)", title, href))
  print(f"✅ [Sloski.si] Znaleziono: {len(articles)}")
  return articles


def check_siol(page):
  soup = fetch_html_playwright(page, "https://siol.net/sportal/zimski-sporti/skoki")
  articles = []
  if soup:
    for a in soup.find_all("a", href=re.compile(r"/sportal/zimski-sporti/.+")):
      title = a.get_text(" ", strip=True)
      if len(title) > 20 and not title.lower().startswith("zimski sporti"):
        href = a["href"]
        url = href if href.startswith("http") else "https://siol.net" + href
        articles.append(("Siol.net (SLO)", title, url))
  print(f"✅ [Siol.net] Znaleziono: {len(articles)}")
  return articles


def check_skoky(page):
  soup = fetch_html_playwright(page, "https://www.skoky.net/")
  articles = []
  if soup:
    for a in soup.find_all("a", href=True):
      href = a["href"]
      title = a.get_text(" ", strip=True)
      if (
          "skoky.net/" in href
          and len(title) > 18
          and not any(
              x in href
              for x in [
                  "/kategorie/",
                  "/tag/",
                  "/author/",
                  "/kontakt",
                  "/redakce",
                  "/kalendar",
                  "#",
              ]
          )
      ):
        articles.append(("Skoky.net (CZE)", title, href))
  print(f"✅ [Skoky.net] Znaleziono: {len(articles)}")
  return articles


def check_swissski(page):
  articles = []
  # 1. Próba przez oficjalną sitemapę XML Swiss-Ski (omija RODO i JS, zawiera wszystkie najnowsze newsy)
  try:
    res = requests.get(
        "https://www.swiss-ski.ch/sitemap.xml",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    if res.status_code == 200:
      # Szukamy sub-sitemap lub bezpośrednich linków z newsami ze skoków
      sub_sitemaps = re.findall(
          r"<loc>(https://www\.swiss-ski\.ch/[^<]*sitemap[^<]*)</loc>", res.text
      )
      urls_to_scan = [res.text]
      for sm in sub_sitemaps[:5]:
        r = requests.get(sm, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
          urls_to_scan.append(r.text)

      for xml_text in urls_to_scan:
        for loc in re.findall(
            r"<loc>(https://www\.swiss-ski\.ch/skispringen/news/[^<]+)</loc>",
            xml_text,
        ):
          if loc.rstrip("/").endswith("/news"):
            continue
          slug = loc.rstrip("/").split("/")[-1]
          title = slug.replace("-", " ").capitalize()
          articles.append(("Swiss-Ski (SUI)", title, loc))
  except Exception as e:
    print(f"❌ Swiss-Ski sitemap błąd: {e}")

  # 2. Jeśli sitemapa nie zwróciła wyników, używamy Playwrighta z obejściem Shadow DOM Usercentrics
  if not articles:
    try:
      page.goto(
          "https://www.swiss-ski.ch/skispringen/news/",
          wait_until="networkidle",
          timeout=35000,
      )
      page.wait_for_timeout(2000)
      # Klikamy przycisk w Shadow DOM (#usercentrics-root) przez JS
      page.evaluate("""() => {
        const root = document.querySelector('#usercentrics-root');
        if (root && root.shadowRoot) {
          const btns = root.shadowRoot.querySelectorAll('button');
          for (const b of btns) {
            if (b.innerText && (b.innerText.includes('akzeptieren') || b.innerText.includes('Accept'))) {
              b.click();
              break;
            }
          }
        }
      }""")
      page.wait_for_timeout(3000)
      page.mouse.wheel(0, 2000)
      page.wait_for_timeout(3000)
      soup = BeautifulSoup(page.content(), "html.parser")
      for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/skispringen/news/" in href and not href.rstrip("/").endswith("/news"):
          title = a.get_text(" ", strip=True)
          parent = a.find_parent(["article", "div", "li"])
          if len(title) < 15 and parent:
            h = parent.find(["h1", "h2", "h3", "h4"])
            if h:
              title = h.get_text(" ", strip=True)
          if len(title) > 15:
            url = (
                href
                if href.startswith("http")
                else "https://www.swiss-ski.ch/" + href.lstrip("/")
            )
            articles.append(("Swiss-Ski (SUI)", title, url))
    except Exception as e:
      print(f"❌ Swiss-Ski Playwright błąd: {e}")

  print(f"✅ [Swiss-Ski] Znaleziono: {len(articles)}")
  return articles


def check_fisi(page):
  articles = []
  try:
    feed = feedparser.parse("https://www.fisi.org/categoria/salto/feed/")
    for entry in feed.entries:
      if entry.get("title") and entry.get("link"):
        articles.append(
            ("FISI (ITA)", entry.title.strip(), entry.link.strip())
        )
  except Exception:
    pass

  soup = fetch_html_playwright(page, "https://www.fisi.org/categoria/salto/")
  if soup:
    for tag in soup.find_all(["nav", "footer"]):
      tag.decompose()
    for h in soup.find_all(["h2", "h3", "h4"]):
      a = h.find("a", href=True)
      if a and "fisi.org/" in a["href"]:
        title = a.get_text(" ", strip=True)
        if len(title) > 15:
          articles.append(("FISI (ITA)", title, a["href"]))
  print(f"✅ [FISI] Znaleziono: {len(articles)}")
  return articles


def check_usaskijumping(page):
  articles = []
  try:
    feed = feedparser.parse("https://usaskijumping.com/feed/")
    for entry in feed.entries:
      if entry.get("title") and entry.get("link"):
        articles.append(
            ("USA Ski Jumping (USA)", entry.title.strip(), entry.link.strip())
        )
  except Exception:
    pass

  soup = fetch_html_playwright(page, "https://usaskijumping.com")
  if soup:
    for tag in soup.find_all(["nav", "footer"]):
      tag.decompose()
    for h in soup.find_all(["h2", "h3", "h4"]):
      a = h.find("a", href=True)
      if a and "usaskijumping.com/" in a["href"]:
        title = a.get_text(" ", strip=True)
        if len(title) > 15:
          articles.append(("USA Ski Jumping (USA)", title, a["href"]))
  print(f"✅ [USA Ski Jumping] Znaleziono: {len(articles)}")
  return articles


def check_delo(page):
  keywords = [
      "prevc",
      "smučarski skoki",
      "skakalec",
      "zajc",
      "lanišek",
      "oblak",
      "jančar",
      "kos",
      "pertile",
  ]
  soup = fetch_html_playwright(page, "https://www.delo.si/sport/zimski-sporti")
  articles = []
  if soup:
    for tag in soup.find_all(["nav", "footer"]):
      tag.decompose()
    for a in soup.find_all("a", href=re.compile(r"/sport/zimski-sporti/.+")):
      href = a["href"]
      url = href if href.startswith("http") else "https://www.delo.si" + href
      title = a.get_text(" ", strip=True)
      parent = a.find_parent(["article", "div", "li"])
      context_text = (
          parent.get_text(" ", strip=True).lower() if parent else title.lower()
      )
      if len(title) < 15 and parent:
        h = parent.find(["h1", "h2", "h3", "h4"])
        if h:
          title = h.get_text(" ", strip=True)

      if len(title) > 15 and any(
          kw in context_text or kw in url.lower() for kw in keywords
      ):
        articles.append(("Delo.si (SLO)", title, url))
  print(f"✅ [Delo.si] Znaleziono: {len(articles)}")
  return articles


def check_dsv(page):
  soup = fetch_html_playwright(
      page, "https://www.deutscherskiverband.de/skisprung", wait_ms=4500
  )
  articles = []
  if soup:
    for tag in soup.find_all(["nav", "footer", "header"]):
      tag.decompose()
    for a in soup.find_all("a", href=True):
      href = a["href"]
      if any(
          bad in href
          for bad in [
              "facebook.com",
              "instagram.com",
              "youtube.com",
              "/impressum",
              "/datenschutz",
              "mailto:",
          ]
      ):
        continue
      if href.rstrip("/").endswith("/skisprung"):
        continue
      title = a.get_text(" ", strip=True)
      if len(title) < 20:
        parent = a.find_parent(["article", "div", "li", "section"])
        if parent:
          h = parent.find(["h1", "h2", "h3", "h4"])
          if h:
            title = h.get_text(" ", strip=True)
      if len(title) > 22 and len(href) > 12:
        url = (
            href
            if href.startswith("http")
            else "https://www.deutscherskiverband.de/" + href.lstrip("/")
        )
        articles.append(("DSV (GER)", title, url))

    if not articles:
      sample = [a.get("href") for a in soup.find_all("a", href=True)[:8]]
      print(f"   🔎 Debug DSV linki: {sample}")

  print(f"✅ [DSV (GER)] Znaleziono: {len(articles)}")
  return articles


def main():
  history = load_history()
  is_first_run = len(history) == 0

  all_found = []
  all_found.extend(check_yle())

  with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="de-DE",
    )
    page = context.new_page()

    all_found.extend(check_blick(page))
    all_found.extend(check_sloski(page))
    all_found.extend(check_siol(page))
    all_found.extend(check_skoky(page))
    all_found.extend(check_swissski(page))
    all_found.extend(check_fisi(page))
    all_found.extend(check_usaskijumping(page))
    all_found.extend(check_delo(page))
    all_found.extend(check_dsv(page))

    browser.close()

  unique_articles = {}
  for source, title, url in all_found:
    clean_url = url.split("?")[0] if "yle.fi" not in url else url
    if clean_url not in unique_articles:
      unique_articles[clean_url] = (source, title)

  new_count = 0
  for url, (source, title) in unique_articles.items():
    if url not in history:
      history.append(url)
      new_count += 1
      if not is_first_run:
        send_discord(source, title, url)

  print(f"📊 Nowe artykuły dodane w tym cyklu: {new_count}")
  save_history(history)


if __name__ == "__main__":
  main()
