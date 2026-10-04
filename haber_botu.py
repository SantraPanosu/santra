# bot.py
import os
import re
import json
import time
import random
import logging
import shutil
import subprocess
import html
from pathlib import Path
import feedparser
import requests
from groq import Groq
from instagrapi import Client
from instagrapi.exceptions import ClientError
from requests.exceptions import RequestException
from playwright.sync_api import sync_playwright

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# --- Env / Secrets ---
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")

if not IG_USERNAME or not IG_PASSWORD or not GROQ_API_KEY:
    logging.error("HATA: IG_USERNAME, IG_PASSWORD veya GROQ_API_KEY eksik.")
    raise SystemExit("Secrets eksik. GitHub Secrets ayarlarını kontrol et.")

client = Groq(api_key=GROQ_API_KEY)

# --- Konfig ---
RSS_KAYNAKLARI = [
    "https://www.fanatik.com.tr/rss/anasayfa",
    "https://www.fotomac.com.tr/rss/anasayfa.xml",
    "https://www.sporx.com/rss.php",
    "https://www.ntv.com.tr/spor.rss"
]

YEDEK = ["https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1080"]
HAFIZA = "paylasilanlar.json"
DESIGN_TEMPLATE = "tasarim.html"   # <-- burada tasarım dosya adı
FILLED_HTML = "design_filled.html"
OUTPUT_IMAGE = "santra_haber.jpg"
LOCAL_BG = "bg_image.jpg"
SESSION_FILE = "ig_session.json"
MAX_HISTORY = 150

# --- Yardımcı fonksiyonlar ---
def safe_load_json(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def gecmisi_yukle():
    return safe_load_json(HAFIZA)

def gecmiye_kaydet(baslik, resim_yolu):
    paylasilanlar = gecmisi_yukle()
    paylasilanlar.append(baslik)
    try:
        with open(HAFIZA, "w", encoding="utf-8") as f:
            json.dump(paylasilanlar[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("Hafiza yazma hatasi: %s", e)

    # Git push (sadece Actions ortamında)
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        return
    try:
        subprocess.run(["git", "config", "--global", "user.name", "Bot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@santra.com"], check=True)
        subprocess.run(["git", "add", HAFIZA], check=True)
        if os.path.exists(resim_yolu):
            subprocess.run(["git", "add", resim_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Guncelleme [skip ci]"], check=True)
        remote = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPOSITORY}.git"
        subprocess.run(["git", "push", remote, "HEAD:main"], check=True)
        logging.info("Hafiza pushlandi.")
    except subprocess.CalledProcessError as e:
        logging.warning("Git push hatasi: %s", e)

def haberleri_cek():
    paylasilanlar = set(gecmisi_yukle())
    haberler = []
    for rss in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:6]:
                title = getattr(entry, "title", None)
                if not title or title in paylasilanlar:
                    continue
                gorsel = random.choice(YEDEK)
                if hasattr(entry, "media_content"):
                    try:
                        gorsel = entry.media_content[0].get('url', gorsel)
                    except Exception:
                        pass
                elif hasattr(entry, "links"):
                    for l in entry.links:
                        if l.get('type','').startswith('image'):
                            gorsel = l.get('href', gorsel)
                            break
                haberler.append({'baslik': title, 'metin': entry.get('description',''), 'gorsel': gorsel})
        except Exception as e:
            logging.debug("RSS parse hatasi %s: %s", rss, e)
            continue
    if not haberler:
        return None
    return random.choice(haberler)

# --- AI parse güvenli ---
def parse_ai_json(cevap):
    s = cevap.replace("```json", "").replace("```", "").strip()
    match = re.search(r'\{.*\}', s, re.DOTALL)
    if not match:
        raise ValueError("AI'den JSON bulunamadi")
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        fixed = candidate.replace("'", '"')
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        return json.loads(fixed)

def ozgunlestir(haber):
    logging.info("Yapay zeka ile orjinal metin olusturuluyor...")
    prompt = (
        'Su spor haberini incele ve SADECE JSON formatinda ver. '
        'Baska hicbir kelime yazma: {"baslik":"kisa baslik","ozet":"1 cumle","aciklama":"kisa","detayli_metin":"uzun text"}. '
        'Haber: ' + (haber['baslik'] or '') + ' - ' + (haber.get('metin','') or '')
    )
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b",
            max_completion_tokens=2048,
            reasoning_effort="medium"
        )
        cevap = chat.choices[0].message.content
        return parse_ai_json(cevap)
    except Exception as e:
        logging.error("AI ozgunlestirme hatasi: %s", e)
        raise

# --- Görsel indirme ve tasarım entegrasyonu ---
def indir(url, hedef):
    try:
        r = requests.get(url, timeout=20, stream=True)
        r.raise_for_status()
        with open(hedef, "wb") as f:
            shutil.copyfileobj(r.raw, f)
        return True
    except Exception as e:
        logging.warning("Indirme hatasi %s -> %s : %s", url, hedef, e)
        return False

def prepare_background(gorsel_url):
    if not gorsel_url:
        gorsel_url = YEDEK[0]
    ok = indir(gorsel_url, LOCAL_BG)
    if not ok:
        indir(YEDEK[0], LOCAL_BG)
    return os.path.abspath(LOCAL_BG)

def html_escape(s, limit=None):
    if s is None:
        return ""
    if limit:
        s = s[:limit]
    return html.escape(s)

def fill_design(ai, bg_local_path):
    if not os.path.exists(DESIGN_TEMPLATE):
        raise FileNotFoundError(f"{DESIGN_TEMPLATE} bulunamadi. Tasarimi repo'ya ekle.")
    with open(DESIGN_TEMPLATE, "r", encoding="utf-8") as f:
        tpl = f.read()
    bg_url = "file://" + bg_local_path.replace("\\", "/")
    filled = tpl.replace("ARKA_PLAN_GORSELI_BURAYA", bg_url)
    filled = filled.replace("BASLIK_BURAYA", html_escape(ai.get("baslik",""), 220))
    filled = filled.replace("OZET_BURAYA", html_escape(ai.get("ozet",""), 200))
    filled = filled.replace("ACIKLAMA_BURAYA", html_escape(ai.get("aciklama",""), 800))
    with open(FILLED_HTML, "w", encoding="utf-8") as f:
        f.write(filled)
    return os.path.abspath(FILLED_HTML)

def resim_olustur_from_design(ai, gorsel_url):
    bg_path = prepare_background(gorsel_url)
    html_path = fill_design(ai, bg_path)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"], headless=True)
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto("file://" + html_path)
page.wait_for_load_state("networkidle")

# Google Fonts'un yüklenmesini bekle (document.fonts.ready)
try:
    page.wait_for_function("document.fonts.ready.then(()=>true)", timeout=8000)
except Exception:
    # Eğer fonts.ready Promise'i beklenemez veya timeout olursa kısa bir ek bekleme yap
    page.wait_for_timeout(500)

# Küçük ek bekleme, fontların render'ı için güvenlik
page.wait_for_timeout(300)

page.screenshot(path=OUTPUT_IMAGE, type="jpeg", quality=90)

        page.screenshot(path=OUTPUT_IMAGE, type="jpeg", quality=90)
        browser.close()
    return os.path.abspath(OUTPUT_IMAGE)

# --- Hashtag üretimi ---
def generate_hashtags(title, extra_tags=None, max_tags=8):
    extra_tags = extra_tags or []
    words = re.findall(r'\w{4,}', title, flags=re.UNICODE)
    freq = {}
    for w in words:
        w_clean = re.sub(r'[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]', '', w).lower()
        if len(w_clean) < 3:
            continue
        freq[w_clean] = freq.get(w_clean, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    tags = [f"#{w[0].capitalize()}" for w in sorted_words[:3]]
    fixed = ["#Futbol", "#Spor", "#Transfer"]
    tags = tags + fixed + extra_tags
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
        if len(seen) >= max_tags:
            break
    return " ".join(seen)

# --- Instagram yükleme (instagrapi) ---
def instagram_yukle_instagrapi(resim, ai, max_retries=3):
    caption_body = ai.get('detayli_metin','') or ai.get('aciklama','') or ai.get('ozet','')
    caption = "🚨 " + ai.get('baslik','') + "\n\n" + caption_body + "\n\n" + generate_hashtags(ai.get('baslik',''))
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(IG_USERNAME, IG_PASSWORD)
        else:
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.dump_settings(SESSION_FILE)
    except Exception as e:
        logging.warning("IG login sorunu: %s", e)

    attempt = 0
    while attempt < max_retries:
        try:
            media = cl.photo_upload(resim, caption)
            logging.info("Paylasildi: %s", getattr(media, "pk", "unknown"))
            return True
        except (ClientError, RequestException) as e:
            attempt += 1
            wait = 2 ** attempt
            logging.warning("Instagram yukleme hatasi (deneme %d): %s. %d sn bekleniyor.", attempt, e, wait)
            time.sleep(wait)
        except Exception as e:
            logging.error("Beklenmeyen hata Instagram yukleme: %s", e)
            return False
    logging.error("Instagram yukleme basarisiz, tum denemeler tukenmis.")
    return False

# --- Main akış ---
def main():
    logging.info("Bot basladi.")
    haber = haberleri_cek()
    if not haber:
        logging.info("Yeni haber bulunamadi.")
        return

    try:
        ai_veri = ozgunlestir(haber)
    except Exception:
        logging.error("AI'den veri alinamadigi icin islem iptal ediliyor.")
        return

    try:
        resim = resim_olustur_from_design(ai_veri, haber.get('gorsel'))
    except Exception as e:
        logging.error("Resim olusturma hatasi: %s", e)
        return

    gecmiye_kaydet(haber['baslik'], resim)

    ok = instagram_yukle_instagrapi(resim, ai_veri)
    if ok:
        logging.info("Islem tamamlandi: %s", haber['baslik'])
    else:
        logging.error("Islem basarisiz: %s", haber['baslik'])

if __name__ == "__main__":
    main()
