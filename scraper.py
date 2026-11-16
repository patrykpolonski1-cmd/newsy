import json
import os
import re
from bs4 import BeautifulSoup
import feedparser
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
HISTORY_FILE = "history.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}


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


def get_rss(source_name, rss_url, url_must_contain=None):
  articles = []
  try:
    res = requests.get(rss_url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    feed = feedparser.parse(res.content)
    for entry in feed.entries:
      title = entry.get("title", "").strip()
      link = entry.get("link", "").strip()
      if not title or not link:
        continue
      if url_must_contain and url_must_contain not in link:
        continue
      articles.append((source_name, title, link))
  except Exception as e:
    print(f"❌ Błąd {source_name}: {e}")
  print(f"✅ [{source_name}] Znaleziono: {len(articles)}")
  return articles


def get_soup(url):
  try:
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")
  except Exception as e:
    print(f"❌ Błąd pobierania {url}: {e}")
    return None


def check_yle():
  # Cała kategoria Mäkihyppy (tag 18-206418)
  return get_rss(
      "Yle.fi (FIN)",
      "https://feeds.yle.fi/uutiset/v1/recent.rss?concepts=18-206418",
  )


def check_blick():
  # Cały dział /sport/wintersport/skispringen/ (filtrowane wyłącznie po ścieżce URL działu)
  articles = get_rss(
      "Blick (SUI)",
      "https://www.blick.ch/sport/wintersport/rss.xml",
      url_must_contain="/skispringen/",
  )
  # Zapasowo sprawdzamy też bezpośrednio HTML strony działu
  soup = get_soup("https://www.blick.ch/sport/wintersport/skispringen")
  if soup:
    for a in soup.find_all("a", href=re.compile(r"/skispringen/.+-id\d+\.html")):
      href = a["href"]
      title = a.get_text(" ", strip=True)
      if len(title) > 15:
        url = (
            href if href.startswith("http") else "https://www.blick.ch" + href
        )
        articles.append(("Blick (SUI)", title, url))
  return articles


def check_sloski():
  # Cały kanał Słoweńskiego Związku Narciarskiego (Sloski.si)
  return get_rss("Sloski.si (SLO)", "https://www.sloski.si/feed/")


def check_krone():
  # Cały dział Ski Nordisch na Krone.at
  return get_rss("Krone.at (AUT)", "https://www.krone.at/ski-nordisch/rss")


def check_sport_de():
  # Cały dział Skispringen na Sport.de
  return get_rss("Sport.de (GER)", "https://www.sport.de/rss/skispringen/")


def check_siol():
  # Cały dział Skoki na Siol.net
  soup = get_soup("https://siol.net/sportal/zimski-sporti/skoki")
  if not soup:
    print("❌ [Siol.net (SLO)] Błąd połączenia")
    return []
  articles = []
  for a in soup.find_all("a", href=re.compile(r"/sportal/zimski-sporti/.+")):
    title = a.get_text(" ", strip=True)
    if len(title) > 20 and not title.lower().startswith("zimski sporti"):
      url = (
          a["href"]
          if a["href"].startswith("http")
          else "https://siol.net" + a["href"]
      )
      articles.append(("Siol.net (SLO)", title, url))
  print(f"✅ [Siol.net (SLO)] Znaleziono: {len(articles)}")
  return articles


def check_skoky():
  # Cały portal Skoky.net
  return get_rss("Skoky.net (CZE)", "https://www.skoky.net/feed/")


def main():
  history = load_history()
  is_first_run = len(history) == 0

  all_found = []
  all_found.extend(check_yle())
  all_found.extend(check_blick())
  all_found.extend(check_sloski())
  all_found.extend(check_krone())
  all_found.extend(check_sport_de())
  all_found.extend(check_siol())
  all_found.extend(check_skoky())

  unique_articles = {}
  for source, title, url in all_found:
    # Usuwamy parametry śledzące (?utm_...) z linków RSS, żeby nie dublowały się w historii
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
