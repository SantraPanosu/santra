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
    "https://feeds.bbci.co.uk/turkce/rss.xml",
    "https://beinsports.com.tr/rss/haberler",
    "https://www.ntv.com.tr/spor.rss",
    "https://www.cnnturk.com/feed/rss/spor/news",
    "https://www.hurriyet.com.tr/rss/spor",
    "https://www.cumhuriyet.com.tr/rss/kategori/spor-7",
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
        subprocess.run(["git", "config", "--global", "user.name", "SantraBot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@santrapanosu.com"], check=True)
        subprocess.run(["git", "add", HAFIZA_DOSYASI], check=True)
        if os.path.exists(resim_yolu): subprocess.run(["git", "add", resim_yolu], check=True)
        if os.path.exists(aciklama_yolu): subprocess.run(["git", "add", aciklama_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Yeni haber hazirlandi (Gorsel + Aciklama) [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Tum dosyalar GitHub'a kaydedildi!")
    except Exception as e:
        print("Git kayit uyarisi:", e)

def haberleri_cek():
    print("Haberler taraniyor...")
    paylasilanlar = gecmisi_yukle()
    haberler = []
    
    for rss in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:3]:
                baslik = entry.title
                if baslik not in paylasilanlar:
                    gorsel_url = random.choice(YEDEK_GORSELLER)
                    if 'media_content' in entry:
                        gorsel_url = entry.media_content[0]['url']
                    elif 'enclosures' in entry and len(entry.enclosures) > 0:
                        gorsel_url = entry.enclosures[0]['href']
                    
                    aciklama = entry.get('description', '')
                    if gorsel_url in YEDEK_GORSELLER:
                        img_match = re.search(r'src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']', aciklama, re.IGNORECASE)
                        if img_match: gorsel_url = img_match.group(1)
                    
                    haberler.append({'baslik': baslik, 'metin': aciklama, 'gorsel': gorsel_url})
        except Exception:
            pass
            
    if not haberler:
        print("UYARI: Paylasilacak yeni haber bulunamadi!")
        return None
        
    secilen = random.choice(haberler)
    print("SECILEN HABER: " + secilen['baslik'])
    return secilen

def ozgunlestir(haber):
    print("Groq yapay zeka devrede...")
    prompt = "Su haberi incele ve SADECE JSON formatinda ver. Baska hicbir kelime yazma: {\"baslik\":\"kisa\",\"ozet\":\"1 cumle\",\"aciklama\":\"kisa\",\"detayli_metin\":\"uzun\"}. Haber: " + haber['baslik'] + " - " + haber['metin']
    
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
    print("Tasarim giydiriliyor...")
    sablon = """[html]
    [head]
    [style]
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700;900&display=swap');
        body { margin: 0; width: 1080px; height: 1080px; font-family: 'Montserrat', sans-serif; position: relative; overflow: hidden; background-color: #0b121d; }
        .bg-image { position: absolute; top: -5%; left: -5%; width: 110%; height: 110%; background: url('IMG_URL') center/cover no-repeat; filter: blur(15px) brightness(0.35); z-index: 1; }
        .container { position: relative; z-index: 2; height: 1080px; display: flex; flex-direction: column; justify-content: space-between; padding: 60px; box-sizing: border-box; }
        .logo-container { font-size: 55px; font-weight: 900; letter-spacing: 1px; text-transform: uppercase; }
        .logo-santra { color: #00e5ff; }
        .logo-panosu { color: #ff7f00; }
        .card { background-color: #0b121d; border-radius: 20px; padding: 50px; border-left: 12px solid #00e5ff; box-shadow: -5px 0px 40px rgba(0, 229, 255, 0.3); }
        .badge { display: inline-block; background-color: #ff7f00; color: white; padding: 12px 24px; border-radius: 8px; font-weight: 700; font-size: 24px; margin-bottom: 30px; text-transform: uppercase; }
        .title { color: white; font-size: 50px; font-weight: 900; line-height: 1.2; margin: 0 0 25px 0; text-transform: uppercase; }
        .summary { color: #00e5ff; font-size: 32px; font-weight: 700; line-height: 1.4; margin: 0 0 25px 0; }
        .desc { color: #d1d5db; font-size: 26px; font-weight: 500; line-height: 1.5; margin: 0; }
    [/style]
    [/head]
    [body]
        [div class='bg-image'][/div]
        [div class='container']
            [div class='logo-container'][span class='logo-santra']SANTRA[/span] [span class='logo-panosu']PANOSU[/span][/div]
            [div class='card']
                [div class='badge']SPOR GÜNDEMİ[/div]
                [h1 class='title']BASLIK[/h1]
                [h2 class='summary']OZET[/h2]
                [p class='desc']ACIKLAMA[/p]
            [/div]
        [/div]
    [/body]
    [/html]"""
    
    html_icerik = sablon.replace("[", "<").replace("]", ">")
    html_icerik = html_icerik.replace("IMG_URL", gorsel)
    html_icerik = html_icerik.replace("BASLIK", ai["baslik"])
    html_icerik = html_icerik.replace("OZET", ai["ozet"])
    html_icerik = html_icerik.replace("ACIKLAMA", ai["aciklama"])
    
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
    
    print("Resim olusturuldu:", yol)
    return yol

def aciklama_kaydet(ai):
    print("Aciklama dosyasi hazirlaniyor...")
    caption = "🚨 " + ai['baslik'] + "\n\n" + ai['detayli_metin'] + "\n\n#Futbol #Spor #Transfer #Santra"
    yol = os.path.join(os.getcwd(), "aciklama.txt")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(caption)
    return yol

if __name__ == "__main__":
    print("---- SANTRA BOT BASLIYOR ----")
    h = haberleri_cek()
    if h:
        ai_veri = ozgunlestir(h)
        resim = resim_olustur(ai_veri, h['gorsel'])
        aciklama = aciklama_kaydet(ai_veri)
        gecmiye_kaydet(h['baslik'], resim, aciklama)
    print("---- ISLEM BITTI ----")
