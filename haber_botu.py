import os
import random
import re
import json
import subprocess
import time
import feedparser
from groq import Groq
from playwright.sync_api import sync_playwright

# --- HASSAS BİLGİLER GITHUB SECRETS'TEN OTOMATİK ÇEKİLİR ---
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY or not IG_USERNAME or not IG_PASSWORD:
    raise ValueError("HATA: Gerekli ortam değişkenleri (Secrets) eksik! Lütfen GitHub Secrets ayarlarını kontrol edin.")

client = Groq(api_key=GROQ_API_KEY)

# Tüm Haber Kaynakları Havuzu
RSS_KAYNAKLARI = [
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

YEDEK_GORSELLER = [
    "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1080",
    "https://images.unsplash.com/photo-1518605368461-1e1e12db801b?q=80&w=1080",
    "https://images.unsplash.com/photo-1574629810360-7efbbe195018?q=80&w=1080",
    "https://images.unsplash.com/photo-1522778119026-d647f0596c20?q=80&w=1080",
    "https://images.unsplash.com/photo-1556056504-5c7696c4c28d?q=80&w=1080"
]

HAFIZA_DOSYASI = "paylasilanlar.json"

def gecmisi_yukle():
    if os.path.exists(HAFIZA_DOSYASI):
        with open(HAFIZA_DOSYASI, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def gecmiye_kaydet(baslik, resim_yolu):
    paylasilanlar = gecmisi_yukle()
    paylasilanlar.append(baslik)
    if len(paylasilanlar) > 150:
        paylasilanlar = paylasilanlar[-150:]
    with open(HAFIZA_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(paylasilanlar, f, ensure_ascii=False, indent=4)
    
    try:
        subprocess.run(["git", "config", "--global", "user.name", "SantraBot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@santrapanosu.com"], check=True)
        
        subprocess.run(["git", "add", HAFIZA_DOSYASI], check=True)
        if os.path.exists(resim_yolu):
            subprocess.run(["git", "add", resim_yolu], check=True)
            
        subprocess.run(["git", "commit", "-m", "Hafiza ve ornek gorsel guncellendi [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Hafıza ve GÖRSEL GitHub deposuna başarıyla kaydedildi! Dosyalarından kontrol edebilirsin.")
    except Exception as e:
        print(f"Git kayıt uyarısı: {e}")

def haberleri_cek():
    paylasilanlar = gecmisi_yukle()
    toplanan_yeni_haberler = []
    
    for secilen_rss in RSS_KAYNAKLARI:
        print(f"Taranıyor: {secilen_rss}")
        try:
            feed = feedparser.parse(secilen_rss)
            if not feed.entries:
                continue
                
            for entry in feed.entries[:5]:
                baslik = entry.title
                if baslik not in paylasilanlar:
                    gorsel_url = random.choice(YEDEK_GORSELLER)
                    if 'media_content' in entry:
                        gorsel_url = entry.media_content[0]['url']
                    elif 'enclosures' in entry and len(entry.enclosures) > 0:
                        gorsel_url = entry.enclosures[0]['href']
                    elif 'links' in entry:
                        for link in entry.links:
                            if 'image' in link.get('type', ''):
                                gorsel_url = link.href
                                break
                                
                    aciklama_metni = entry.get('description', '')
                    if not gorsel_url or gorsel_url in YEDEK_GORSELLER:
                        img_match = re.search(r'src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']', aciklama_metni, re.IGNORECASE)
                        if img_match:
                            gorsel_url = img_match.group(1)
                    
                    toplanan_yeni_haberler.append({
                        'orjinal_baslik': baslik,
                        'orjinal_metin': aciklama_metni,
                        'gorsel_url': gorsel_url
                    })
        except Exception as e:
            pass
            
    if not toplanan_yeni_haberler:
        print("UYARI: Paylaşılacak yeni haber bulunamadı! Daha önce paylaşılanlar atlanıyor.")
        return None
        
    secilen_haber = random.choice(toplanan_yeni_haberler)
    print(f"SEÇİLEN TAZE HABER: {secilen_haber['orjinal_baslik']}")
    return secilen_haber

def yapay_zeka_ile_ozgunlestir(haber_verisi):
    print("Groq yapay zeka devrede, bülten hazırlanıyor...")
    
    # Çoklu satır kopyalama hatasını önlemek için güvenli format:
    prompt = (
        "Aşağıdaki spor haberini incele ve Instagram için profesyonel bir içerik üret.\n"
        "Senden 4 şey istiyorum ve çıktıyı KESİNLİKLE sadece şu JSON formatında ver, başka hiçbir şey yazma:\n"
        "{\n"
        "  \"baslik\": \"Görsel üzerine yazılacak çarpıcı ve büyük ana başlık\",\n"
        "  \"ozet\": \"Görselde yer alacak 1 cümlelik vurucu özet\",\n"
        "  \"aciklama\": \"Görselde yer alacak 2-3 cümlelik kısa kart açıklaması\",\n"
        "  \"detayli_metin\": \"Instagram açıklaması için; haberin detaylarını anlatan profesyonel metin.\"\n"
        "}\n\n"
        "Haber Başlığı: " + haber_verisi['orjinal_baslik'] + "\n"
        "Haber İçeriği: " + haber_verisi['orjinal_metin']
    )
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",  # Yeni aldığın API anahtarı ile %100 açık olan model
    )
    
    cevap = chat_completion.choices[0].message.content
    temiz_metin = cevap.replace("```json", "").replace("```", "").strip()
    return json.loads(temiz_metin)

def resim_olustur(ai_veri, gorsel_url):
    print("Tasarım giydiriliyor...")
    
    if not os.path.exists("tasarim.html"):
        print("UYARI: tasarim.html dosyası bulunamadı, basit bir şablon oluşturuluyor...")
        # Çoklu satır hatasını önlemek için güvenli HTML formatı:
        basit_sablon = (
            "\n"
            "\n"
            "
