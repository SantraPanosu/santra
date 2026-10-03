import os
import feedparser
import google.generativeai as genai
import json

# API Anahtarını GitHub'ın gizli kasasından alıyoruz (Kimse çalamasın diye)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Ücretsiz ve süper hızlı model
model = genai.GenerativeModel('gemini-1.5-flash')

def haberleri_cek(rss_url):
    print(f"Haberler çekiliyor: {rss_url}")
    feed = feedparser.parse(rss_url)
    
    if not feed.entries:
        print("Haber bulunamadı.")
        return None
        
    en_yeni_haber = feed.entries[0]
    
    # Haberin orjinal görselini yakalama
    gorsel_url = ""
    if 'media_content' in en_yeni_haber:
        gorsel_url = en_yeni_haber.media_content[0]['url']
    elif 'links' in en_yeni_haber:
        for link in en_yeni_haber.links:
            if 'image' in link.get('type', ''):
                gorsel_url = link.href
                break
    
    haber_verisi = {
        'orjinal_baslik': en_yeni_haber.title,
        'orjinal_metin': en_yeni_haber.get('description', ''),
        'gorsel_url': gorsel_url
    }
    return haber_verisi

def yapay_zeka_ile_ozgunlestir(haber_verisi):
    print("Yapay zeka metni yeniden kurguluyor...")
    
    prompt = f"""
    Aşağıdaki haberi okuyarak Instagram/Twitter gibi platformlar için modern bir haber kartı metni oluştur.
    Senden 3 şey istiyorum:
    1. Çarpıcı, merak uyandıran modern bir 'Ana Başlık' (baslik)
    2. 1 cümlelik vurucu 'Ne Oldu?' özeti (ozet)
    3. Okuyucuyu yormayacak 2-3 cümlelik kısa açıklama (aciklama)
    
    Format ZORUNLULUĞU: Sadece aşağıdaki JSON formatında çıktı ver, başka hiçbir yorum veya kelime yazma.
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
    
    try:
        ai_icerik = json.loads(temiz_metin)
        return ai_icerik
    except Exception as hata:
        print("Yapay zeka metni düzgün oluşturamadı:", hata)
        return None

if __name__ == "__main__":
    # Test için TRT Haber'in verilerini kullanıyoruz
    RSS_KAYNAGI = "https://www.trthaber.com/xml_mobile.php" 
    
    orjinal_haber = haberleri_cek(RSS_KAYNAGI)
    
    if orjinal_haber:
        islenmis_haber = yapay_zeka_ile_ozgunlestir(orjinal_haber)
        
        if islenmis_haber:
            print("\n--- HABER BASARIYLA ISLENDI ---")
            print(f"BAŞLIK: {islenmis_haber['baslik']}")
            print(f"ÖZET: {islenmis_haber['ozet']}")
            print(f"AÇIKLAMA: {islenmis_haber['aciklama']}")
            print(f"GÖRSEL LİNKİ: {orjinal_haber['gorsel_url']}")
