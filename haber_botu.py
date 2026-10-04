#!/usr/bin/env python3
# haber_botu.py
# Basit, güvenli ve çalışır halde bir Instagram haber botu örneği.
# - RSS kaynaklarını çeker
# - İlk uygun haberi alır
# - Basit bir HTML oluşturur
# - Playwright ile HTML'den JPEG screenshot alır
# - instagrapi ile görseli Instagram'a yükler
#
# Ortam değişkenleri:
# IG_USERNAME, IG_PASSWORD, GROQ_API_KEY (opsiyonel, eğer kullanıyorsan)
# GITHUB_REPOSITORY ve GITHUB_TOKEN CI için opsiyonel

import os
import sys
import tempfile
import time
import logging
from datetime import datetime
from pathlib import Path

import feedparser
from playwright.sync_api import sync_playwright
from instagrapi import Client

# ---------------------------
# RSS kaynakları (istek üzerine eklendi)
# ---------------------------
RSS_SOURCES = [
    "https://www.fanatik.com.tr/rss/anasayfa",
    "https://www.fotomac.com.tr/rss/anasayfa.xml",
    "https://www.sporx.com/rss.php",
    "https://feeds.bbci.co.uk/turkce/rss.xml",
    "https://beinsports.com.tr/rss/haberler",
    "https://www.transfermarkt.com.tr/rss/news",
    "https://www.trthaber.com/spor_articles.rss",
    "https://www.ntv.com.tr/spor.rss",
    "https://www.cnnturk.com/feed/rss/spor/news",
    "https://www.hurriyet.com.tr/rss/spor",
    "https://www.cumhuriyet.com.tr/rss/kategori/spor-7",
    "https://www.milliyet.com.tr/rss/rssnew/sporvadisi/tumu.xml",
    "https://www.sabah.com.tr/rss/spor.xml",
    "https://www.aksam.com.tr/rss/spor.rss",
    "https://www.yenisafak.com/rss/spor"
]

# ---------------------------
# Ayarlar
# ---------------------------
OUTPUT_DIR = Path(tempfile.gettempdir()) / "haber_botu"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_IMAGE = OUTPUT_DIR / "haber.jpg"
HTML_FILE = OUTPUT_DIR / "haber.html"
LOG_LEVEL = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


# ---------------------------
# RSS çekme
# ---------------------------
def fetch_latest_entry(sources):
    """
    Verilen RSS kaynaklarından en taze ve uygun ilk entry'yi döndürür.
    Döndürülen dict: {'title':..., 'link':..., 'summary':..., 'published':...}
    """
    logging.info("RSS kaynaklarından haber çekiliyor...")
    best = None
    for url in sources:
        try:
            d = feedparser.parse(url)
            if not d or not d.entries:
                logging.debug("Kaynak boş veya parse edilemedi: %s", url)
                continue
            for entry in d.entries:
                # Basit filtre: başlık ve link olmalı
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                published = entry.get("published", entry.get("updated", ""))
                if not title or not link:
                    continue
                candidate = {
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": published
                }
                # İlk uygun haberi al (basit davranış)
                logging.info("Haber bulundu: %s (kaynak: %s)", title, url)
                return candidate
        except Exception as e:
            logging.warning("RSS parse hatası %s: %s", url, e)
    logging.info("Hiçbir uygun haber bulunamadı.")
    return None


# ---------------------------
# HTML oluşturma
# ---------------------------
def render_html_for_entry(entry, html_path: Path):
    """
    Basit bir HTML oluşturur. Daha gelişmiş tasarım istersen burayı değiştir.
    """
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    link = entry.get("link", "")
    published = entry.get("published", "")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; margin:0; padding:0; background:#fff; color:#111; }}
    .card {{ width:1200px; height:630px; padding:40px; box-sizing:border-box; display:flex; flex-direction:column; justify-content:space-between; }}
    .title {{ font-size:48px; font-weight:700; line-height:1.05; margin-bottom:20px; }}
    .summary {{ font-size:22px; color:#333; max-height:300px; overflow:hidden; }}
    .meta {{ font-size:14px; color:#666; margin-top:20px; }}
    .footer {{ font-size:12px; color:#999; }}
    a {{ color:#1a73e8; text-decoration:none; }}
  </style>
</head>
<body>
  <div class="card">
    <div>
      <div class="title">{title}</div>
      <div class="summary">{summary}</div>
    </div>
    <div>
      <div class="meta">Kaynak: <a href="{link}">{link}</a></div>
      <div class="footer">Oluşturuldu: {now} • Yayın tarihi: {published}</div>
    </div>
  </div>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    logging.info("HTML dosyası oluşturuldu: %s", html_path)


# ---------------------------
# Playwright ile screenshot alma
# ---------------------------
def make_screenshot_from_html(html_path: Path, output_image: Path):
    """
    Playwright (Chromium) kullanarak verilen HTML dosyasının ekran görüntüsünü alır.
    """
    logging.info("Playwright ile screenshot alınıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1200, "height": 630})
        page = context.new_page()
        page.goto("file://" + str(html_path.resolve()))
        page.wait_for_load_state("networkidle")

        # Google Fonts veya diğer fontların yüklenmesini bekle (güvenlik için try/except)
        try:
            page.wait_for_function("document.fonts.ready.then(()=>true)", timeout=8000)
        except Exception:
            page.wait_for_timeout(500)

        # Küçük ek bekleme, fontların render'ı için güvenlik
        page.wait_for_timeout(300)

        # EKRAN GÖRÜNTÜSÜ AL (aynı girintide olmalı)
        page.screenshot(path=str(output_image), type="jpeg", quality=90)

        context.close()
        browser.close()
    logging.info("Screenshot alındı: %s", output_image)


# ---------------------------
# Instagram'a yükleme
# ---------------------------
def post_to_instagram(image_path: Path, caption: str, username: str, password: str):
    """
    instagrapi kullanarak görseli yükler.
    """
    logging.info("Instagram'a giriş yapılıyor: %s", username)
    cl = Client()
    try:
        cl.login(username, password)
    except Exception as e:
        logging.error("Instagram login hatası: %s", e)
        raise

    logging.info("Görsel yükleniyor: %s", image_path)
    try:
        media = cl.photo_upload(str(image_path), caption)
        logging.info("Yükleme başarılı. Media id: %s", getattr(media, "pk", "unknown"))
    except Exception as e:
        logging.error("Instagram yükleme hatası: %s", e)
        raise
    finally:
        try:
            cl.logout()
        except Exception:
            pass


# ---------------------------
# Ana akış
# ---------------------------
def main():
    logging.info("Bot başlatılıyor...")
    # Ortam değişkenleri
    ig_user = os.environ.get("IG_USERNAME")
    ig_pass = os.environ.get("IG_PASSWORD")

    if not ig_user or not ig_pass:
        logging.error("IG_USERNAME veya IG_PASSWORD ortam değişkenleri eksik.")
        sys.exit(1)

    entry = fetch_latest_entry(RSS_SOURCES)
    if not entry:
        logging.info("Gönderilecek haber bulunamadı. Çıkılıyor.")
        return

    # HTML oluştur
    render_html_for_entry(entry, HTML_FILE)

    # Screenshot al
    try:
        make_screenshot_from_html(HTML_FILE, OUTPUT_IMAGE)
    except Exception as e:
        logging.error("Screenshot alınırken hata: %s", e)
        sys.exit(1)

    # Caption hazırla (basit)
    title = entry.get("title", "")
    link = entry.get("link", "")
    caption = f"{title}\n\nKaynak: {link}"

    # Instagram'a yükle
    try:
        post_to_instagram(OUTPUT_IMAGE, caption, ig_user, ig_pass)
    except Exception as e:
        logging.error("Instagram'a yükleme başarısız: %s", e)
        sys.exit(1)

    logging.info("İşlem tamamlandı.")


if __name__ == "__main__":
    main()
