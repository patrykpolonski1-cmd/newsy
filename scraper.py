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
    json.dump(history[-2500:], f, ensure_ascii=False, indent=2)


def send_discord(source, title, url):
  if not WEBHOOK_URL:
    print(f"[TEST] {source}: {title} -> {url}")
    return
  payload = {"content": f"📡 **{source}**\n**{title}**\n{url}"}
  requests.post(WEBHOOK_URL, json=payload, timeout=10)


def accept_cookies(page):
  # Klika przyciski RODO zarówno na głównej stronie, jak i w ramkach iframe (Sourcepoint/Usercentrics)
  button_texts = [
      "Alle akzeptieren",
      "Einverstanden",
      "Akzeptieren",
      "Zustimmen",
      "Accept all",
  ]
  for frame in [page] + page.frames:
    for text in button_texts:
      try:
        btn = frame.get_by_role(
            "button", name=re.compile(text, re.IGNORECASE)
        ).first
        if btn.is_visible(timeout=500):
          btn.click(timeout=1000)
          page.wait_for_timeout(2000)
          return
      except Exception:
        pass


def fetch_html_playwright(page, url, wait_ms=3000):
  try:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    accept_cookies(page)
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
    for a in soup.find_all("a", href=re.compile(r"-id\d+\.html")):
      href = a["href"]
      title = a.get_text(" ", strip=True)
      if len(title) > 15:
        url = (
            href if href.startswith("http") else "https://www.blick.ch" + href
        )
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


def check_krone(page):
  soup = fetch_html_playwright(page, "https://www.krone.at/ski-nordisch")
  articles = []
  if soup:
    for a in soup.find_all("a", href=re.compile(r"krone\.at/\d+|^/\d+")):
      href = a["href"]
      title = a.get_text(" ", strip=True)
      if len(title) > 18:
        url = (
            href if href.startswith("http") else "https://www.krone.at" + href
        )
        articles.append(("Krone.at (AUT)", title, url))
  print(f"✅ [Krone.at] Znaleziono: {len(articles)}")
  return articles


def check_sport_de(page):
  # Zaktualizowany adres z Twojego zrzutu ekranu: sport.de/wintersport/magazin/
  soup = fetch_html_playwright(
      page, "https://www.sport.de/wintersport/magazin/"
  )
  articles = []
  if soup:
    for a in soup.find_all("a", href=True):
      href = a["href"]
      title = a.get_text(" ", strip=True)
      # Artykuły na sport.de mają w linku /news/ lub kończą się ID artykułu
      if (
          ("/news/" in href or re.search(r"-\d{5,}/?$", href))
          and len(title) > 18
      ):
        url = (
            href if href.startswith("http") else "https://www.sport.de" + href
        )
        articles.append(("Sport.de (GER)", title, url))
  print(f"✅ [Sport.de] Znaleziono: {len(articles)}")
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
    all_found.extend(check_krone(page))
    all_found.extend(check_sport_de(page))
    all_found.extend(check_siol(page))
    all_found.extend(check_skoky(page))

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
