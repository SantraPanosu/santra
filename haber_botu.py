import os, random, re, json, subprocess, time, feedparser
from groq import Groq
from playwright.sync_api import sync_playwright

IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY or not IG_USERNAME or not IG_PASSWORD:
    raise ValueError("HATA: Gerekli ortam degiskenleri (Secrets) eksik! Lutfen GitHub Secrets ayarlarini kontrol edin.")

client = Groq(api_key=GROQ_API_KEY)

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
        subprocess.run(["git", "commit", "-m", "Hafiza ve gorsel guncellendi [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Hafıza ve GÖRSEL GitHub deposuna başarıyla kaydedildi!")
    except Exception as e:
        pass

def haberleri_cek():
    paylasilanlar = gecmisi_yukle()
    toplanan_yeni_haberler = []
    
    for secilen_rss in RSS_KAYNAKLARI:
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
        except Exception:
            pass
            
    if not toplanan_yeni_haberler:
        return None
        
    return random.choice(toplanan_yeni_haberler)

def yapay_zeka_ile_ozgunlestir(haber_verisi):
    prompt = "Su haberi incele ve SADECE JSON formatinda ver. Baska hicbir kelime yazma: {\"baslik\":\"kisa\",\"ozet\":\"1 cumle\",\"aciklama\":\"kisa\",\"detayli_metin\":\"uzun\"}. Haber: " + haber_verisi['orjinal_baslik'] + " - " + haber_verisi['orjinal_metin']
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        max_completion_tokens=2048,
        reasoning_effort="medium"
    )
    
    cevap = chat_completion.choices[0].message.content
    temiz_metin = cevap.replace("```json", "").replace("```", "").strip()
    
    json_match = re.search(r'\{.*?\}', temiz_metin.replace('\n', ''), re.IGNORECASE | re.DOTALL)
    if json_match:
        temiz_metin = json_match.group(0)
        
    return json.loads(temiz_metin)

def resim_olustur(ai_veri, gorsel_url):
    html_icerik = "\x3Chtml\x3E\x3Cbody style=\"background:url('" + gorsel_url + "');background-size:cover;color:#fff;padding:50px;font-family:sans-serif;\"\x3E\x3Cdiv style=\"background:rgba(0,0,0,0.6);padding:40px;border-radius:20px;\"\x3E\x3Ch1 style=\"font-size:3.5em\"\x3E" + ai_veri["baslik"] + "\x3C/h1\x3E\x3Ch2 style=\"color:#f39c12;font-size:2.5em\"\x3E" + ai_veri["ozet"] + "\x3C/h2\x3E\x3Cp style=\"font-size:1.8em\"\x3E" + ai_veri["aciklama"] + "\x3C/p\x3E\x3C/div\x3E\x3C/body\x3E\x3C/html\x3E"
    
    with open("gecici.html", "w", encoding="utf-8") as f:
        f.write(html_icerik)

    yol = os.path.join(os.getcwd(), "santra_haber.jpg")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto("file://" + os.path.abspath("gecici.html"))
        page.screenshot(path=yol, type="jpeg")
        browser.close()
    return yol

def instagram_yukle(resim, ai):
    caption = "🚨 " + ai['baslik'] + "\n\n" + ai['detayli_metin'] + "\n\n#Futbol #Spor #Transfer #Santra"
    
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        context = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
        time.sleep(5)
        
        page.wait_for_selector("input[name='username']", timeout=15000)
        page.locator("input[name='username']").fill(IG_USERNAME)
        page.locator("input[name='password']").fill(IG_PASSWORD)
        page.locator("button[type='submit']").click()
        time.sleep(10)
        
        page.goto("https://www.instagram.com/create/style/", timeout=60000)
        time.sleep(5)
        
        page.locator("input[type='file']").set_input_files(resim)
        time.sleep(3)
        
        for _ in range(2):
            try:
                page.locator("button:has-text('İleri'), button:has-text('Next')").click()
                time.sleep(2)
            except Exception:
                pass
                
        page.locator("div[aria-label='Write a caption...'], textarea").fill(caption)
        time.sleep(2)
        page.locator("button:has-text('Paylaş'), button:has-text('Share')").click()
        time.sleep(10)
        b.close()

if __name__ == "__main__":
    h = haberleri_cek()
    if h:
        ai_veri = yapay_zeka_ile_ozgunlestir(h)
        resim = resim_olustur(ai_veri, h['gorsel_url'])
        gecmiye_kaydet(h['orjinal_baslik'], resim)
        instagram_yukle(resim, ai_veri)
