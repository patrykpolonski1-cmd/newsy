import json
import os
import re
from bs4 import BeautifulSoup
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
HISTORY_FILE = "history.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_history():
  if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
      return json.load(f)
  return []


def save_history(history):
  with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    # Trzymamy ostatnie 300 linków, żeby plik nie puchł w nieskończoność
    json.dump(history[-300:], f, ensure_ascii=False, indent=2)


def send_discord(source, title, url):
  if not WEBHOOK_URL:
    print(f"[TEST] {source}: {title} -> {url}")
    return
  payload = {"content": f"📡 **{source}**\n**{title}**\n{url}"}
  requests.post(WEBHOOK_URL, json=payload, timeout=10)


def get_soup(url):
  try:
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")
  except Exception as e:
    print(f"Błąd pobierania {url}: {e}")
    return None


def check_yle():
  soup = get_soup("https://yle.fi/t/18-206418/fi")
  if not soup:
    return []
  articles = []
  for a in soup.find_all("a", href=re.compile(r"^/a/74-\d+")):
    title = a.get_text(strip=True)
    if len(title) > 15:
      articles.append(("Yle.fi (FIN)", title, "https://yle.fi" + a["href"]))
  return articles


def check_fisi():
  soup = get_soup("https://fisi.org/salto/")
  if not soup:
    return []
  articles = []
  for h in soup.find_all(["h2", "h3", "h4"]):
    a = h.find("a", href=True)
    if a and "fisi.org" in a["href"]:
      title = a.get_text(strip=True)
      if len(title) > 15:
        articles.append(("FISI (ITA)", title, a["href"]))
  return articles


def check_blick():
  soup = get_soup("https://www.blick.ch/sport/wintersport/skispringen/")
  if not soup:
    return []
  articles = []
  for a in soup.find_all(
      "a", href=re.compile(r"/sport/wintersport/skispringen/.+-id\d+\.html")
  ):
    title = a.get_text(strip=True)
    if len(title) > 20:
      url = (
          a["href"]
          if a["href"].startswith("http")
          else "https://www.blick.ch" + a["href"]
      )
      articles.append(("Blick (SUI)", title, url))
  return articles


def check_sport_de():
  soup = get_soup("https://www.sport.de/skispringen/magazin/")
  if not soup:
    return []
  articles = []
  for a in soup.find_all("a", href=re.compile(r"/news/ne\d+/")):
    title = a.get_text(strip=True)
    if len(title) > 15:
      url = (
          a["href"]
          if a["href"].startswith("http")
          else "https://www.sport.de" + a["href"]
      )
      articles.append(("Sport.de (GER)", title, url))
  return articles


def check_skoky():
  soup = get_soup("https://www.skoky.net/")
  if not soup:
    return []
  articles = []
  for h in soup.find_all(["h2", "h3"]):
    a = h.find("a", href=True)
    if a:
      title = a.get_text(strip=True)
      if len(title) > 15:
        url = (
            a["href"]
            if a["href"].startswith("http")
            else "https://www.skoky.net/" + a["href"].lstrip("/")
        )
        articles.append(("Skoky.net (CZE)", title, url))
  return articles


def check_siol():
  soup = get_soup("https://siol.net/sportal/zimski-sporti")
  if not soup:
    return []
  articles = []
  keywords = [
      "skok",
      "polet",
      "prevc",
      "lanišek",
      "zajc",
      "kos",
      "planica",
      "skakal",
  ]
  for a in soup.find_all("a", href=re.compile(r"/sportal/zimski-sporti/.+")):
    title = a.get_text(strip=True)
    if len(title) > 20 and any(kw in title.lower() for kw in keywords):
      url = (
          a["href"]
          if a["href"].startswith("http")
          else "https://siol.net" + a["href"]
      )
      articles.append(("Siol.net (SLO)", title, url))
  return articles


def main():
  history = load_history()
  # Pierwsze uruchomienie: zapisuje obecne artykuły bez spamowania Discorda
  is_first_run = len(history) == 0

  all_found = []
  all_found.extend(check_yle())
  all_found.extend(check_fisi())
  all_found.extend(check_blick())
  all_found.extend(check_sport_de())
  all_found.extend(check_skoky())
  all_found.extend(check_siol())

  # Usuwamy duplikaty z tej samej iteracji
  unique_articles = {}
  for source, title, url in all_found:
    if url not in unique_articles:
      unique_articles[url] = (source, title)

  for url, (source, title) in unique_articles.items():
    if url not in history:
      history.append(url)
      if not is_first_run:
        send_discord(source, title, url)

  save_history(history)


if __name__ == "__main__":
  main()
