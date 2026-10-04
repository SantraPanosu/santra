#!/usr/bin/env python3
# haber_botu.py
# Instagram haber botu — RSS çek, HTML oluştur, screenshot al, Instagram'a yükle
# TOTP (IG_2FA_SECRET) destekli, retry + exponential backoff, session persistence

import os
import sys
import tempfile
import time
import logging
import random
from datetime import datetime
from pathlib import Path

import feedparser
from playwright.sync_api import sync_playwright
from instagrapi import Client

# ---------------------------
# RSS kaynakları
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
    logging.info("RSS kaynaklarından haber çekiliyor...")
    for url in sources:
        try:
            d = feedparser.parse(url)
            if not d or not d.entries:
                logging.debug("Kaynak boş veya parse edilemedi: %s", url)
                continue
            for entry in d.entries:
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
    logging.info("Playwright ile screenshot alınıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1200, "height": 630})
        page = context.new_page()
        page.goto("file://" + str(html_path.resolve()))
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_function("document.fonts.ready.then(()=>true)", timeout=8000)
        except Exception:
            page.wait_for_timeout(500)
        page.wait_for_timeout(300)
        page.screenshot(path=str(output_image), type="jpeg", quality=90)
        context.close()
        browser.close()
    logging.info("Screenshot alındı: %s", output_image)

# ---------------------------
# Instagram'a yükleme (güncel, fallback'li)
# ---------------------------
def post_to_instagram(image_path: Path, caption: str, username: str, password: str,
                      max_retries: int = 6, base_delay: float = 5.0):
    """
    Instagram login + upload:
    - retry + exponential backoff
    - TOTP destekli (IG_2FA_SECRET veya IG_2FA_CODE)
    - fallback: eğer instagrapi.login() two_factor_callback kabul etmiyorsa,
      otomatik TOTP üretip verification_code veya two_factor_login ile deneyecek.
    """
    logging.info("Instagram'a giriş denemesi: %s", username)
    cl = Client()
    try:
        cl.user_agent = "Instagram 300.0.0.0 Android (30/11; 420dpi; 1080x2340; OnePlus; OnePlus6T; OnePlus6T; qcom; tr_TR)"
    except Exception:
        pass

    def get_totp_code():
        secret = os.environ.get("IG_2FA_SECRET")
        if secret:
            try:
                import pyotp
                return pyotp.TOTP(secret).now()
            except Exception as e:
                logging.warning("TOTP üretimi başarısız: %s", e)
        manual = os.environ.get("IG_2FA_CODE")
        if manual:
            return manual
        return None

    def two_factor_callback(username_inner):
        code = get_totp_code()
        if code:
            logging.info("TOTP kodu üretildi otomatik olarak.")
            return code
        logging.error("Two-factor kodu bulunamadı. IG_2FA_SECRET veya IG_2FA_CODE ayarla.")
        raise Exception("Two-factor code not available in environment.")

    def challenge_handler(username_inner, choice):
        logging.error("Instagram challenge_required tetiklendi. Manuel müdahale gerekli.")
        raise Exception("Instagram challenge_required: manual verification required.")

    session_file = Path(tempfile.gettempdir()) / "ig_session.json"

    # LOGIN RETRY with fallback for instagrapi versions
    for attempt in range(1, max_retries + 1):
        try:
            if session_file.exists():
                logging.info("Kayıtlı session yükleniyor: %s", session_file)
                cl.load_settings(str(session_file))

            # İlk tercih: modern instagrapi with two_factor_callback
            try:
                cl.login(username, password, two_factor_callback=two_factor_callback, challenge_handler=challenge_handler)
                logging.info("Instagram login başarılı (two_factor_callback).")
                break
            except TypeError as te:
                # Eğer login() unexpected keyword arg hatası veriyorsa fallback yap
                msg = str(te).lower()
                if "unexpected keyword" in msg or "two_factor_callback" in msg:
                    logging.warning("two_factor_callback desteklenmiyor, fallback yöntemleri deneniyor.")
                    # Fallback 1: verification_code param ile login (bazı sürümlerde desteklenir)
                    code = get_totp_code()
                    if code:
                        try:
                            cl.login(username, password, verification_code=code)
                            logging.info("Instagram login başarılı (verification_code).")
                            break
                        except Exception as e_ver:
                            logging.warning("verification_code ile login başarısız: %s", e_ver)
                    # Fallback 2: two_factor_login metodu (bazı sürümlerde mevcut)
                    try:
                        code = get_totp_code()
                        if code:
                            # some instagrapi versions have two_factor_login(username, password, verification_code)
                            try:
                                cl.two_factor_login(username, password, code)
                                logging.info("Instagram login başarılı (two_factor_login).")
                                break
                            except TypeError:
                                # some variants accept only code
                                try:
                                    cl.two_factor_login(code)
                                    logging.info("Instagram login başarılı (two_factor_login code-only).")
                                    break
                                except Exception as e_tf:
                                    logging.warning("two_factor_login fallback başarısız: %s", e_tf)
                    except Exception as e:
                        logging.warning("two_factor_login denemesi hata verdi: %s", e)
                    # Eğer tüm fallbackler başarısızsa, raise or continue to backoff
                    raise te
                else:
                    # TypeError farklıysa yeniden raise et
                    raise
            except Exception as e:
                # Normal hata (ör. 400, 429, challenge_required vb.)
                raise

        except Exception as e:
            msg = str(e).lower()
            logging.warning("Login denemesi %d başarısız: %s", attempt, msg)
            if "out of date" in msg or "upgrade your app" in msg:
                logging.error("Instagram uygulama sürümüyle ilgili hata: %s", msg)
                logging.error("Öneriler: instagrapi sürümünü güncelle veya user_agent değiştir.")
                raise
            if "challenge_required" in msg:
                logging.error("challenge_required: manuel doğrulama gerekli.")
                raise
            if "429" in msg or "too many" in msg or "rate" in msg:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 3)
                logging.warning("Rate limit benzeri hata. %s saniye bekleniyor (attempt %d).", delay, attempt)
                time.sleep(delay)
            else:
                time.sleep(min(base_delay * attempt, 60))
            if attempt == max_retries:
                logging.error("Login için maksimum deneme sayısına ulaşıldı.")
                raise

    # Başarılı login sonrası session kaydet
    try:
        cl.dump_settings(str(session_file))
        logging.info("Session kaydedildi: %s", session_file)
    except Exception:
        logging.debug("Session kaydetme başarısız, devam ediliyor.")

    # UPLOAD RETRY
    for attempt in range(1, max_retries + 1):
        try:
            media = cl.photo_upload(str(image_path), caption)
            logging.info("Yükleme başarılı. Media id: %s", getattr(media, "pk", "unknown"))
            break
        except Exception as e:
            msg = str(e).lower()
            logging.warning("Upload denemesi %d başarısız: %s", attempt, msg)
            if "429" in msg or "too many" in msg or "rate" in msg:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 3)
                logging.warning("Upload rate limit. %s saniye bekleniyor (attempt %d).", delay, attempt)
                time.sleep(delay)
            else:
                time.sleep(min(base_delay * attempt, 30))
            if attempt == max_retries:
                logging.error("Upload için maksimum deneme sayısına ulaşıldı.")
                raise

    try:
        cl.logout()
    except Exception:
        pass

# ---------------------------
# Ana akış
# ---------------------------
def main():
    logging.info("Bot başlatılıyor...")
    ig_user = os.environ.get("IG_USERNAME")
    ig_pass = os.environ.get("IG_PASSWORD")

    if not ig_user or not ig_pass:
        logging.error("IG_USERNAME veya IG_PASSWORD ortam değişkenleri eksik.")
        sys.exit(1)

    entry = fetch_latest_entry(RSS_SOURCES)
    if not entry:
        logging.info("Gönderilecek haber bulunamadı. Çıkılıyor.")
        return

    render_html_for_entry(entry, HTML_FILE)

    try:
        make_screenshot_from_html(HTML_FILE, OUTPUT_IMAGE)
    except Exception as e:
        logging.error("Screenshot alınırken hata: %s", e)
        sys.exit(1)

    title = entry.get("title", "")
    link = entry.get("link", "")
    caption = f"{title}\n\nKaynak: {link}"

    try:
        post_to_instagram(OUTPUT_IMAGE, caption, ig_user, ig_pass)
    except Exception as e:
        logging.error("Instagram'a yükleme başarısız: %s", e)
        sys.exit(1)

    logging.info("İşlem tamamlandı.")

if __name__ == "__main__":
    main()
