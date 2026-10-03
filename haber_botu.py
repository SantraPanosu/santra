import os
import feedparser
import google.generativeai as genai
import json
import traceback
from playwright.sync_api import sync_playwright

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")

if not GEMINI_API_KEY:
    raise ValueError("HATA: GEMINI_API_KEY bulunamadı!")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def haberleri_cek(rss_url):
    print(f"Haberler çekiliyor: {rss_url}")
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        raise Exception("RSS kaynağından haber bulunamadı!")
        
    en_yeni_haber = feed.entries[0]
    gorsel_url = "https://images.unsplash.com/photo-1518605368461-1e1e12db801b?q=80&w=1080" 
    
    if 'media_content' in en_yeni_haber:
        gorsel_url = en_yeni_haber.media_content[0]['url']
    elif 'links' in en_yeni_haber:
        for link in en_yeni_haber.links:
            if 'image' in link.get('type', ''):
                gorsel_url = link.href
                break
    
    print(f"Haber çekildi: {en_yeni_haber.title}")
    return {
        'orjinal_baslik': en_yeni_haber.title,
        'orjinal_metin': en_yeni_haber.get('description', ''),
        'gorsel_url': gorsel_url
    }

def yapay_zeka_ile_ozgunlestir(haber_verisi):
    print("Yapay zeka devrede...")
    prompt = f"""
    Aşağıdaki haberi okuyarak Instagram için modern bir haber kartı metni oluştur.
    Senden 3 şey istiyorum:
    1. Çarpıcı, merak uyandıran modern bir 'Ana Başlık' (baslik)
    2. 1 cümlelik vurucu 'Ne Oldu?' özeti (ozet)
    3. Okuyucuyu yormayacak 2-3 cümlelik kısa açıklama (aciklama)
    
    Sadece aşağıdaki JSON formatında çıktı ver, başka hiçbir şey yazma:
    {{
        "baslik": "...",
        "ozet": "...",
        "aciklama": "..."
    }}
    
    Haber Başlığı: {haber_verisi['orjinal_baslik']}
    Haber İçeriği: {haber_verisi['orjinal_metin']}
    """
    response = model.generate_content(prompt)
    temiz_metin = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(temiz_metin)

def resim_olustur(ai_veri, gorsel_url):
    print("Tasarım giydiriliyor...")
    with open("tasarim.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    html = html.replace("Beşiktaş'tan Flaş Hamle: Kadro Planlamasında Yeni Hedefler Belli Oldu!", ai_veri["baslik"])
    html = html.replace("Siyah-beyazlı yönetim, transfer döneminin kapanmasına kısa süre kala eksik bölgeler için düğmeye bastı.", ai_veri["ozet"])
    html = html.replace("Teknik heyetin sunduğu detaylı rapor doğrultusunda hareket eden komite, alternatifli bir oyuncu havuzu oluşturdu. Gelişmelerin hafta sonuna kadar netleşmesi bekleniyor.", ai_veri["aciklama"])
    html = html.replace("https://images.unsplash.com/photo-1518605368461-1e1e12db801b?q=80&w=1080&auto=format&fit=crop", gorsel_url)
    html = html.replace("https://images.unsplash.com/photo-1518605368461-1e1e12db801b?q=80&w=1080", gorsel_url)
    
    with open("gecici.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("Ekran görüntüsü alınıyor...")
    resim_yolu = os.path.join(os.getcwd(), "santra_haber.jpg")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = browser.new_page(set_viewport_size={"width": 1080, "height": 1080})
        page.goto(f"file://{os.path.abspath('gecici.html')}")
        page.locator(".card").screenshot(path=resim_yolu, type="jpeg", quality=90)
        browser.close()
        
    print(f"BAŞARILI: {resim_yolu} oluşturuldu.")
    return "santra_haber.jpg"

if __name__ == "__main__":
    RSS_KAYNAGI = "https://www.trthaber.com/spor_articles.rss" 
    
    haber = haberleri_cek(RSS_KAYNAGI)
    if haber:
        islenmis = yapay_zeka_ile_ozgunlestir(haber)
        if islenmis:
            resim_dosyasi = resim_olustur(islenmis, haber['gorsel_url'])
            print("Süreç başarıyla tamamlandı!")
