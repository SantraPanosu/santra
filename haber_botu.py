import os, random, re, json, subprocess, time, feedparser
from groq import Groq
from playwright.sync_api import sync_playwright

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("HATA: GROQ_API_KEY eksik!")
    exit(1)

client = Groq(api_key=GROQ_API_KEY)

RSS_KAYNAKLARI = [
    "https://www.fanatik.com.tr/rss/anasayfa",
    "https://www.fotomac.com.tr/rss/anasayfa.xml",
    "https://www.sporx.com/rss.php",
    "https://beinsports.com.tr/rss/haberler",
    "https://www.ntv.com.tr/spor.rss",
    "https://www.cnnturk.com/feed/rss/spor/news",
    "https://www.hurriyet.com.tr/rss/spor",
    "https://www.sabah.com.tr/rss/spor.xml",
    "https://www.yenisafak.com/rss/spor"
]

YEDEK_GORSELLER = [
    "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1080",
    "https://images.unsplash.com/photo-1518605368461-1e1e12db801b?q=80&w=1080",
    "https://images.unsplash.com/photo-1574629810360-7efbbe195018?q=80&w=1080",
    "https://images.unsplash.com/photo-1556056504-5c7696c4c28d?q=80&w=1080"
]

HAFIZA_DOSYASI = "paylasilanlar.json"
YASAKLI_KELIMELER = ["misli", "iddaa", "bahis", "kupon", "oran", "casino", "slot", "yatırım", "bonus", "günün maçları", "hangi kanalda", "saat kaçta"]

def gecmisi_yukle():
    if os.path.exists(HAFIZA_DOSYASI):
        with open(HAFIZA_DOSYASI, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return []
    return []

def gecmiye_kaydet(baslik, resim_yolu, aciklama_yolu):
    print("Hafiza ve dosyalar guncelleniyor...")
    paylasilanlar = gecmisi_yukle()
    paylasilanlar.append(baslik)
    if len(paylasilanlar) > 150: paylasilanlar = paylasilanlar[-150:]
    with open(HAFIZA_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(paylasilanlar, f, ensure_ascii=False, indent=4)
    
    try:
        subprocess.run(["git", "config", "--global", "user.name", "SahaEkraniBot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@sahaekrani.com"], check=True)
        subprocess.run(["git", "add", HAFIZA_DOSYASI], check=True)
        if os.path.exists(resim_yolu): subprocess.run(["git", "add", resim_yolu], check=True)
        if os.path.exists(aciklama_yolu): subprocess.run(["git", "add", aciklama_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Yeni gercek spor haberi hazirlandi (SahaEkrani) [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Tum dosyalar GitHub'a kaydedildi!")
    except Exception as e:
        print("Git kayit uyarisi:", e)

def haberleri_cek():
    print("Haberler taraniyor ve filtreleniyor...")
    paylasilanlar = gecmisi_yukle()
    haberler = []
    
    for rss in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:5]:
                baslik = entry.title
                aciklama = entry.get('description', '')
                
                metin_butun = (baslik + " " + aciklama).lower()
                yasakli_varmi = any(kelime in metin_butun for kelime in YASAKLI_KELIMELER)
                
                if not yasakli_varmi and baslik not in paylasilanlar:
                    gorsel_url = random.choice(YEDEK_GORSELLER)
                    if 'media_content' in entry:
                        gorsel_url = entry.media_content[0]['url']
                    elif 'enclosures' in entry and len(entry.enclosures) > 0:
                        gorsel_url = entry.enclosures[0]['href']
                    
                    if gorsel_url in YEDEK_GORSELLER:
                        img_match = re.search(r'src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']', aciklama, re.IGNORECASE)
                        if img_match: gorsel_url = img_match.group(1)
                    
                    haberler.append({'baslik': baslik, 'metin': aciklama, 'gorsel': gorsel_url})
        except Exception:
            pass
            
    if not haberler:
        print("UYARI: Paylasilacak uygun haber bulunamadi!")
        return None
        
    secilen = random.choice(haberler)
    print("SECILEN GERCEK HABER: " + secilen['baslik'])
    return secilen

def ozgunlestir(haber):
    print("Groq yapay zeka devrede...")
    prompt = (
        "Sen profesyonel bir spor editörüsün. Aşağıdaki haberi incele. "
        "Eğer haber 'Günün maçları', 'Hangi kanalda?', 'Maç programı' veya takvim listesi gibi boş/tarihsel bir içerikse; "
        "bunu reddet ve yerine gerçek bir olay (transfer, sakatlık, röportaj, kriz, kulüp açıklaması) formatına çevir. "
        "SADECE JSON formatinda ver, baska hicbir kelime yazma: "
        "{\"baslik\":\"kisa ve carpici baslik\",\"ozet\":\"1 cumlelik ozet\",\"aciklama\":\"kisa\",\"detayli_metin\":\"detayli aciklama\"}. "
        "Haber: " + haber['baslik'] + " - " + haber['metin']
    )
    
    chat = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        max_completion_tokens=2048,
        reasoning_effort="medium"
    )
    
    cevap = chat.choices[0].message.content
    temiz_metin = cevap.replace("```json", "").replace("```", "").strip()
    
    match = re.search(r'\{.*?\}', temiz_metin.replace('\n', ''), re.IGNORECASE | re.DOTALL)
    if match: temiz_metin = match.group(0)
        
    return json.loads(temiz_metin)

def resim_olustur(ai, gorsel):
    print("SahaEkrani tasarimi template.html üzerinden giydiriliyor...")
    
    # template.html dosyasını oku
    with open("template.html", "r", encoding="utf-8") as f:
        html_icerik = f.read()
    
    # Değişkenleri yerine yerleştir
    html_icerik = html_icerik.replace("IMG_URL", gorsel)
    html_icerik = html_icerik.replace("BASLIK", ai["baslik"])
    html_icerik = html_icerik.replace("OZET", ai["ozet"])
    
    with open("gecici.html", "w", encoding="utf-8") as f:
        f.write(html_icerik)

    yol = os.path.join(os.getcwd(), "santra_haber.jpg")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto("file://" + os.path.abspath("gecici.html"), wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.screenshot(path=yol, type="jpeg", quality=90)
        browser.close()
    
    print("SahaEkrani gorseli olusturuldu:", yol)
    return yol

def aciklama_kaydet(ai):
    print("Aciklama dosyasi hazirlaniyor...")
    caption = "🚨 " + ai['baslik'] + "\n\n" + ai['detayli_metin'] + "\n\n#SahaEkrani #Futbol #Spor #Transfer"
    yol = os.path.join(os.getcwd(), "aciklama.txt")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(caption)
    return yol

if __name__ == "__main__":
    print("---- SAHA EKRANI BOT BASLIYOR ----")
    h = haberleri_cek()
    if h:
        ai_veri = ozgunlestir(h)
        resim = resim_olustur(ai_veri, h['gorsel'])
        aciklama = aciklama_kaydet(ai_veri)
        gecmiye_kaydet(h['baslik'], resim, aciklama)
    print("---- ISLEM BITTI ----")
