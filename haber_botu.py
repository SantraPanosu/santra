import os, random, re, json, subprocess, time, feedparser
from groq import Groq
from playwright.sync_api import sync_playwright

IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY or not IG_USERNAME or not IG_PASSWORD:
    raise ValueError("HATA: Secrets eksik! Lutfen GitHub Secrets ayarlarini kontrol et.")

client = Groq(api_key=GROQ_API_KEY)

RSS_KAYNAKLARI = [
    "https://www.fanatik.com.tr/rss/anasayfa",
    "https://www.fotomac.com.tr/rss/anasayfa.xml",
    "https://www.sporx.com/rss.php",
    "https://www.ntv.com.tr/spor.rss"
]

YEDEK = ["https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1080"]
HAFIZA = "paylasilanlar.json"

def gecmisi_yukle():
    if os.path.exists(HAFIZA):
        with open(HAFIZA, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return []
    return []

def gecmiye_kaydet(baslik, resim_yolu):
    paylasilanlar = gecmisi_yukle()
    paylasilanlar.append(baslik)
    with open(HAFIZA, "w", encoding="utf-8") as f:
        json.dump(paylasilanlar[-150:], f, ensure_ascii=False, indent=4)
    try:
        subprocess.run(["git", "config", "--global", "user.name", "Bot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@santra.com"], check=True)
        subprocess.run(["git", "add", HAFIZA], check=True)
        if os.path.exists(resim_yolu): subprocess.run(["git", "add", resim_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Guncelleme [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception:
        pass

def haberleri_cek():
    paylasilanlar = gecmisi_yukle()
    haberler = []
    for rss in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:3]:
                if entry.title not in paylasilanlar:
                    gorsel = random.choice(YEDEK)
                    if 'media_content' in entry: gorsel = entry.media_content[0]['url']
                    haberler.append({'baslik': entry.title, 'metin': entry.get('description', ''), 'gorsel': gorsel})
        except Exception:
            pass
    if not haberler: return None
    return random.choice(haberler)

def ozgunlestir(haber):
    print("Yapay zeka devrede...")
    prompt = 'Su spor haberini incele ve SADECE JSON formatinda ver. Baska hicbir kelime yazma: {"baslik":"kisa baslik","ozet":"1 cumle","aciklama":"kisa","detayli_metin":"uzun text"}. Haber: ' + haber['baslik'] + ' - ' + haber['metin']
    
    chat = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        max_completion_tokens=2048,
        reasoning_effort="medium"
    )
    cevap = chat.choices[0].message.content
    
    json_match = re.search(r'\{.*?\}', cevap.replace('\n', ''), re.IGNORECASE | re.DOTALL)
    if json_match:
        temiz_metin = json_match.group(0)
    else:
        temiz_metin = cevap.replace("```json", "").replace("```", "").strip()
        
    return json.loads(temiz_metin)

def resim_olustur(ai, gorsel):
    html_icerik = """
{}
{}
{}
{}
""".format(
        gorsel, ai["baslik"], ai["ozet"], ai["aciklama"]
    )

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
    caption = "🚨 " + ai['baslik'] + "\n\n" + ai['detayli_metin'] + "\n\n#Futbol #Spor #Transfer"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        # Gerçek bir tarayıcı kimliği (User-Agent) tanımlıyoruz ki Instagram bot olduğunu anlamasın
        context = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        print("Instagram'a bağlanılıyor...")
        page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
        time.sleep(5) # Sayfanın tam oturması için bekleme
        
        # Kullanıcı adı alanını bekle ve doldur
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
        ai_veri = ozgunlestir(h)
        resim = resim_olustur(ai_veri, h['gorsel'])
        gecmiye_kaydet(h['baslik'], resim)
        instagram_yukle(resim, ai_veri)
