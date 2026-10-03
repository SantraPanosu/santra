import os
import random
import re
import json
import subprocess
import feedparser
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from instagrapi import Client

# --- KENDİ INSTAGRAM BİLGİLERİNİ BURAYA YAZ ---
IG_USERNAME = "KULLANICI_ADIN"
IG_PASSWORD = "SIFREN"
# ----------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("HATA: GEMINI_API_KEY bulunamadı!")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.8-flash')

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

def gecmiye_kaydet(baslik):
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
        subprocess.run(["git", "commit", "-m", "Yeni haber paylasildi, hafiza guncellendi [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Hafıza GitHub deposuna kaydedildi.")
    except Exception as e:
        print(f"Git kayıt uyarısı (Lokal testlerde normaldir): {e}")

def haberleri_cek():
    paylasilanlar = gecmisi_yukle()
    toplanan_yeni_haberler = []
    
    # Hepsini tek tek tarıyoruz
    for secilen_rss in RSS_KAYNAKLARI:
        print(f"Taranıyor: {secilen_rss}")
        try:
            feed = feedparser.parse(secilen_rss)
            if not feed.entries:
                continue
                
            # Her kaynağın son 5 haberini incele
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
            print(f"Kaynak taranırken hata oluştu ({secilen_rss}): {e}")
            
    if not toplanan_yeni_haberler:
        print("UYARI: Tüm kaynaklar tarandı ancak yeni haber bulunamadı!")
        return None
        
    # Toplanan tüm yeni haberler arasından rastgele veya en tazesini seçiyoruz
    secilen_haber = random.choice(toplanan_yeni_haberler)
    print(f"SEÇİLEN TAZE HABER: {secilen_haber['orjinal_baslik']}")
    return secilen_haber

def yapay_zeka_ile_ozgunlestir(haber_verisi):
    print("Yapay zeka devrede, bülten hazırlanıyor...")
    prompt = f"""
    Aşağıdaki spor haberini incele ve Instagram için profesyonel bir içerik üret.
    Senden 4 şey istiyorum ve çıktıyı KESİNLİKLE sadece aşağıdaki JSON formatında ver:
    1. "baslik": Görsel üzerine yazılacak çarpıcı ve büyük ana başlık.
    2. "ozet": Görselde yer alacak 1 cümlelik vurucu özet.
    3. "aciklama": Görselde yer alacak 2-3 cümlelik kısa kart açıklaması.
    4. "detayli_metin": Instagram açıklaması için; haberin tüm detaylarını, arka planını ve analizini anlatan, en az 3-4 paragraftan oluşan profesyonel metin.
    
    JSON formatı dışında asla başka bir şey yazma:
    {{
        "baslik": "...",
        "ozet": "...",
        "aciklama": "...",
        "detayli_metin": "..."
    }}
    
    Haber Başlığı: {haber_verisi['orjinal_baslik']}
    Haber İçeriği: {haber_verisi['orjinal_metin']}
    """
    response = model.generate_content(prompt)
    temiz_metin = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(temiz_metin)

def resim_olustur(ai_veri, gorsel_url):
    print("Tasarım giydiriliyor ve arka plan görseli işleniyor...")
    with open("tasarim.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    html = html.replace("BASLIK_BURAYA", ai_veri["baslik"])
    html = html.replace("OZET_BURAYA", ai_veri["ozet"])
    html = html.replace("ACIKLAMA_BURAYA", ai_veri["aciklama"])
    html = html.replace("ARKA_PLAN_GORSELI_BURAYA", gorsel_url)
    
    with open("gecici.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("Ekran görüntüsü alınıyor...")
    resim_yolu = os.path.join(os.getcwd(), "santra_haber.jpg")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = browser.new_page()
        page.set_viewport_size({"width": 1080, "height": 1080})
        page.goto(f"file://{os.path.abspath('gecici.html')}", wait_until="networkidle")
        page.locator(".card").screenshot(path=resim_yolu, type="jpeg", quality=90)
        browser.close()
        
    print(f"BAŞARILI: {resim_yolu} oluşturuldu.")
    return resim_yolu

def instagrama_yukle(resim_yolu, ai_veri):
    print("Instagram'a otomatik bağlanılıyor...")
    try:
        cl = Client()
        cl.login(IG_USERNAME, IG_PASSWORD)
        
        hashtags = (
            "#SantraPanosu #SporGündemi #Futbol #SüperLig #Transfer "
            "#SonDakika #Galatasaray #Fenerbahçe #Beşiktaş #Trabzonspor "
            "#MilliTakim #Maç #Keşfet #Explore #FootballNews #SporHaberleri"
        )
        
        caption = (
            f"🚨 {ai_veri['baslik']}\n\n"
            f"{ai_veri['detayli_metin']}\n\n"
            "📌 Bu tarz en güncel gelişmelerden anında haberdar olmak için gönderiyi beğenmeyi ve kaydetmeyi unutmayın!\n\n"
            "👇 Sizce bu olay takımınızı nasıl etkiler? Yorumlarda buluşalım!\n\n"
            f"{hashtags}"
        )
        
        cl.photo_upload(resim_yolu, caption)
        print("BAŞARILI: Gönderi başarıyla yayınlandı! ✅")
    except Exception as e:
        print(f"Instagram Paylaşım Hatası: {e}")

if __name__ == "__main__":
    haber = haberleri_cek()
    if haber:
        islenmis = yapay_zeka_ile_ozgunlestir(haber)
        if islenmis:
            resim_dosyasi = resim_olustur(islenmis, haber['gorsel_url'])
            instagrama_yukle(resim_dosyasi, islenmis)
            gecmiye_kaydet(haber['orjinal_baslik'])
            print("Süreç tamamen tamamlandı!")
    else:
        print("HATA: Paylaşılacak yeni haber bulunamadı.")
