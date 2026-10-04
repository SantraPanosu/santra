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
        subprocess.run(["git", "config", "--global", "user.name", "SahaEkraniBot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@sahaekrani.com"], check=True)
        subprocess.run(["git", "add", HAFIZA_DOSYASI], check=True)
        if os.path.exists(resim_yolu): subprocess.run(["git", "add", resim_yolu], check=True)
        if os.path.exists(aciklama_yolu): subprocess.run(["git", "add", aciklama_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Yeni haber hazirlandi (SahaEkrani Gorsel + Aciklama) [skip ci]"], check=True)
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
    print("SahaEkrani tasarimi giydiriliyor...")
    sablon = """[html]
    [head]
    [style]
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,400;0,700;0,900&family=Oswald:wght@500;700&display=swap');
        body, html { margin: 0; padding: 0; width: 1080px; height: 1080px; font-family: 'Montserrat', sans-serif; background-color: #161b22; display: flex; justify-content: center; align-items: center; overflow: hidden; }
        .instagram-post { width: 1080px; height: 1080px; position: relative; background: linear-gradient(135deg, #161b22 0%, #1e252d 100%); color: white; box-sizing: border-box; padding: 60px; display: flex; flex-direction: column; z-index: 1; }
        .bg-pattern { position: absolute; top: 0; left: 0; width: 1080px; height: 1080px; background-image: radial-gradient(circle at 50% 50%, rgba(53, 152, 219, 0.1) 0%, transparent 60%), linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px); background-size: 100% 100%, 50px 50px, 50px 50px; z-index: -2; }
        .bg-image { position: absolute; top: -5%; left: -5%; width: 110%; height: 110%; background-color: #1a2026; background-image: url('IMG_URL'); background-size: cover; background-position: center; filter: blur(20px) brightness(0.25); z-index: -3; }
        .header { display: flex; align-items: center; margin-bottom: 40px; z-index: 2; }
        .logo-container { width: 180px; height: 180px; border-radius: 50%; overflow: hidden; border: 4px solid #3598db; box-shadow: 0 0 30px rgba(53, 152, 219, 0.4); background-color: #151a21; flex-shrink: 0; }
        .logo-container img { width: 100%; height: 100%; object-fit: contain; }
        .header-text { margin-left: 35px; }
        .header-text h1 { font-family: 'Oswald', sans-serif; font-size: 75px; margin: 0; line-height: 0.95; text-transform: uppercase; letter-spacing: 2px; }
        .text-green { color: #5ad54e; }
        .text-white { color: #ffffff; }
        .content-card { flex: 1; background: rgba(26, 32, 38, 0.6); backdrop-filter: blur(25px); -webkit-backdrop-filter: blur(25px); border: 2px solid rgba(53, 152, 219, 0.25); border-radius: 30px; padding: 50px; display: flex; flex-direction: column; justify-content: center; box-shadow: 0 25px 50px rgba(0,0,0,0.6); position: relative; overflow: hidden; }
        .content-card::before { content: ''; position: absolute; left: 0; top: 0; width: 12px; height: 100%; background: linear-gradient(to bottom, #5ad54e, #3598db); }
        .category-badge { display: inline-block; background-color: #5ad54e; color: #161b22; font-weight: 900; font-size: 24px; padding: 8px 22px; border-radius: 8px; margin-bottom: 25px; text-transform: uppercase; align-self: flex-start; box-shadow: 0 0 20px rgba(90, 213, 78, 0.3); }
        .news-title { font-size: 50px; font-weight: 900; line-height: 1.2; margin: 0 0 20px 0; text-transform: uppercase; color: #ffffff; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }
        .news-body { font-size: 28px; line-height: 1.4; color: #e0e0e0; margin: 0; font-weight: 400; }
        .footer { margin-top: 30px; display: flex; justify-content: flex-end; align-items: center; font-size: 24px; color: #7a8a99; font-weight: bold; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 20px; }
        .footer-brand { color: #3598db; }
        .watermark { position: absolute; bottom: -30px; right: -30px; font-size: 200px; font-weight: 900; color: rgba(255,255,255,0.02); z-index: 0; pointer-events: none; font-family: 'Oswald', sans-serif; text-transform: uppercase; }
    [/style]
    [/head]
    [body]
        [div class='instagram-post']
            [div class='bg-image'][/div]
            [div class='bg-pattern'][/div]
            [div class='watermark']SAHA[/div]
            [div class='header']
                [div class='logo-container']
                    [img src='LOGO.jpeg' alt='Saha Ekrani Logo']
                [/div]
                [div class='header-text']
                    [h1 class='text-green']SAHA[/h1]
                    [h1 class='text-white']EKRANI[/h1]
                [/div]
            [/div]
            [div class='content-card']
                [div class='category-badge']SON DAKİKA[/div]
                [h1 class='news-title']BASLIK[/h1]
                [p class='news-body']OZET[/p>
            [/div]
            [div class='footer']
                [span class='footer-brand']@sahaekrani[/span]
            [/div]
        [/div]
    [/body]
    [/html]"""
    
    html_icerik = sablon.replace("[", "<").replace("]", ">")
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
