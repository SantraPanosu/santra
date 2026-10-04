# bot.py
import os
import random
import re
import json
import subprocess
import time
import logging
from datetime import datetime
import feedparser
from groq import Groq
from instagrapi import Client
from instagrapi.exceptions import ClientError, ClientLoginRequired
from requests.exceptions import RequestException

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# --- Env / Secrets ---
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")  # owner/repo, Actions sağlar

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
SESSION_FILE = "ig_session.json"
MAX_HISTORY = 150

# --- Yardımcılar ---
def gecmisi_yukle():
    if os.path.exists(HAFIZA):
        try:
            with open(HAFIZA, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

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
            for entry in feed.entries[:5]:
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

# AI JSON parse güvenli
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

# Basit HTML render + screenshot için Playwright yerine remote image kullanmayi tercih ediyoruz.
# Burada sadece local bir basit HTML olusturup browserless ile screenshot almak yerine
# instagrapi ile direkt fotoğraf yukleyecegiz. Bu fonksiyon gorseli indirip basit bir overlay yapar.
def gorsel_indir_ve_hazirla(url, hedef="santra_haber.jpg"):
    import requests
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        with open(hedef, "wb") as f:
            f.write(r.content)
        return hedef
    except Exception as e:
        logging.warning("Gorsel indirilemedi, yedek kullaniliyor: %s", e)
        # yedek resim URL'sinden indir
        try:
            r = requests.get(YEDEK[0], timeout=15)
            r.raise_for_status()
            with open(hedef, "wb") as f:
                f.write(r.content)
            return hedef
        except Exception as e2:
            logging.error("Yedek resim de indirilemedi: %s", e2)
            raise

# Instagram yukleme - instagrapi ile
def instagram_yukle_instagrapi(resim, ai, max_retries=3):
    caption = "🚨 " + ai.get('baslik','') + "\n\n" + ai.get('detayli_metin','') + "\n\n#Futbol #Spor #Transfer"
    cl = Client()
    # Session dosyasi ile tekrar login onlemek
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(IG_USERNAME, IG_PASSWORD)
        else:
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.dump_settings(SESSION_FILE)
    except Exception as e:
        logging.warning("IG login sorunu: %s", e)
        # Yine de denemeye devam

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

# Main akis
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
        resim = gorsel_indir_ve_hazirla(haber.get('gorsel'))
    except Exception:
        logging.error("Gorsel hazirlanamadi.")
        return

    # Hafizaya kaydet ve push
    gecmiye_kaydet(haber['baslik'], resim)

    # Instagram yukle
    ok = instagram_yukle_instagrapi(resim, ai_veri)
    if ok:
        logging.info("Islem tamamlandi: %s", haber['baslik'])
    else:
        logging.error("Islem basarisiz: %s", haber['baslik'])

if __name__ == "__main__":
    main()
