import os, random, re, json, subprocess, base64, feedparser
from groq import Groq
from playwright.sync_api import sync_playwright

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("HATA: GROQ_API_KEY eksik!")
    exit(1)

client = Groq(api_key=GROQ_API_KEY)

# Tüm ana spor ve futbol RSS kaynakları
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

HAFIZA_DOSYASI = "paylasilanlar.json"

# Yasaklı kelimeler filtresi (Bahis, iddaa, maç programı vb.)
YASAKLI_KELIMELER = [
    "misli",
    "iddaa",
    "bahis",
    "kupon",
    "oran",
    "casino",
    "slot",
    "yatırım",
    "bonus",
    "günün maçları",
    "hangi kanalda",
    "saat kaçta",
    "maç programı",
    "haftanın maçları",
    "yayın akışı"
]


def gecmisi_yukle():
    if os.path.exists(HAFIZA_DOSYASI):
        with open(HAFIZA_DOSYASI, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []


def gecmiye_kaydet(baslik, resim_yolu, aciklama_yolu):
    print("Hafiza ve dosyalar guncelleniyor...")

    paylasilanlar = gecmisi_yukle()

    if baslik not in paylasilanlar:
        paylasilanlar.append(baslik)

    if len(paylasilanlar) > 200:
        paylasilanlar = paylasilanlar[-200:]

    with open(HAFIZA_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(
            paylasilanlar,
            f,
            ensure_ascii=False,
            indent=4
        )

    try:
        subprocess.run(
            [
                "git",
                "config",
                "--global",
                "user.name",
                "SahaEkraniBot"
            ],
            check=True
        )

        subprocess.run(
            [
                "git",
                "config",
                "--global",
                "user.email",
                "bot@sahaekrani.com"
            ],
            check=True
        )

        subprocess.run(
            ["git", "add", HAFIZA_DOSYASI],
            check=True
        )

        if os.path.exists(resim_yolu):
            subprocess.run(
                ["git", "add", resim_yolu],
                check=True
            )

        if os.path.exists(aciklama_yolu):
            subprocess.run(
                ["git", "add", aciklama_yolu],
                check=True
            )

        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Yeni guncel spor haberi hazirlandi (SahaEkrani) [skip ci]"
            ],
            check=True
        )

        subprocess.run(
            ["git", "push"],
            check=True
        )

        print("Tum dosyalar GitHub'a kaydedildi!")

    except Exception as e:
        print("Git kayit uyarisi:", e)


def haberleri_cek():
    print("Tum RSS siteleri tek tek taranıyor ve en yeniler filtreleniyor...")

    paylasilanlar = gecmisi_yukle()
    tum_adaylar = []

    for rss in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(rss)

            for entry in feed.entries[:5]:
                baslik = entry.title.strip()
                aciklama = entry.get('description', '')

                metin_butun = (
                    baslik + " " + aciklama
                ).lower()

                yasakli_varmi = any(
                    kelime in metin_butun
                    for kelime in YASAKLI_KELIMELER
                )

                if not yasakli_varmi and baslik not in paylasilanlar:
                    gorsel_url = None

                    if hasattr(entry, 'media_content') and entry.media_content:
                        gorsel_url = entry.media_content[0].get('url')

                    elif hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                        gorsel_url = entry.media_thumbnail[0].get('url')

                    elif hasattr(entry, 'enclosures') and entry.enclosures:
                        for enc in entry.enclosures:
                            if 'image' in enc.get('type', ''):
                                gorsel_url = enc.get('href')
                                break

                        if not gorsel_url and entry.enclosures:
                            gorsel_url = entry.enclosures[0].get('href')

                    if not gorsel_url:
                        html_text = aciklama

                        if hasattr(entry, 'content'):
                            for c in entry.content:
                                html_text += " " + c.get('value', '')

                        img_match = re.search(
                            r'src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp|avif))["\']',
                            html_text,
                            re.IGNORECASE
                        )

                        if img_match:
                            gorsel_url = img_match.group(1)

                    if gorsel_url:
                        tum_adaylar.append(
                            {
                                'baslik': baslik,
                                'metin': aciklama,
                                'gorsel': gorsel_url
                            }
                        )

        except Exception as e:
            print(f"RSS tarama hatasi ({rss}):", e)
            pass

    if not tum_adaylar:
        print("UYARI: Paylasilmamis yeni haber bulunamadi!")
        return None

    secilen = tum_adaylar[0]

    print(
        "SEÇİLEN EN YENİ VE BENZERSİZ HABER: "
        + secilen['baslik']
    )

    return secilen


def ozgunlestir(haber):
    print("Groq yapay zeka devrede (Kesin Gerçeklik Modu)...")

    prompt = (
        "Sen profesyonel bir spor editörüsün. Aşağıdaki güncel haberi incele. "
        "KESİNLİKLE KAFANDAN YENİ BİRŞEY, UYDURMA TRANSFER VEYA RAKAM EKLEME. "
        "Sadece verilen kaynak metindeki gerçekleri baz alarak düzenle. "
        "SADECE JSON formatinda ver, baska hicbir kelime yazma: "
        "{\"baslik\":\"orijinal baslik\",\"ozet\":\"1 cumlelik ozet\",\"aciklama\":\"kisa\",\"detayli_metin\":\"detay\"}. "
        "Kaynak Başlık: " + haber['baslik'] + " | Kaynak Metin: " + haber['metin']
    )

    chat = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        model="openai/gpt-oss-120b",
        max_completion_tokens=2048,
        reasoning_effort="medium"
    )

    cevap = chat.choices[0].message.content

    temiz_metin = (
        cevap
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    match = re.search(
        r'\{.*?\}',
        temiz_metin.replace('\n', ''),
        re.IGNORECASE | re.DOTALL
    )

    if match:
        temiz_metin = match.group(0)

    return json.loads(temiz_metin)


def resim_olustur(ai, gorsel):
    print("SahaEkrani tam ekran sablon tasarimi olusturuluyor...")

    logo_base64 = ""

    if os.path.exists("LOGO.jpeg"):
        with open("LOGO.jpeg", "rb") as f:
            logo_base64 = base64.b64encode(
                f.read()
            ).decode('utf-8')

    logo_src = (
        f"data:image/jpeg;base64,{logo_base64}"
        if logo_base64
        else ""
    )

    safe_gorsel = (
        gorsel
        .replace("'", "%27")
        .replace('"', "%22")
    )

    sablon = """





BASLIK
OZET

"""

    html_icerik = sablon.replace(
        "SAFE_GORSEL",
        safe_gorsel
    )

    html_icerik = html_icerik.replace(
        "LOGO_SRC",
        logo_src
    )

    html_icerik = html_icerik.replace(
        "BASLIK",
        ai["baslik"]
    )

    html_icerik = html_icerik.replace(
        "OZET",
        ai["ozet"]
    )

    yol = os.path.join(
        os.getcwd(),
        "santra_haber.jpg"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--no-sandbox"]
        )

        page = browser.new_page(
            viewport={
                "width": 1080,
                "height": 1080
            }
        )

        page.set_content(
            html_icerik,
            wait_until="load"
        )

        page.wait_for_timeout(3000)

        page.screenshot(
            path=yol,
            type="jpeg",
            quality=90
        )

        browser.close()

    print(
        "SahaEkrani gorseli olusturuldu:",
        yol
    )

    return yol


def aciklama_kaydet(ai):
    print("Aciklama dosyasi hazirlaniyor...")

    caption = (
        "🚨 "
        + ai['baslik']
        + "\n\n"
        + ai['detayli_metin']
        + "\n\n"
        + "#SahaEkrani #Futbol #Spor #Transfer"
    )

    yol = os.path.join(
        os.getcwd(),
        "aciklama.txt"
    )

    with open(
        yol,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(caption)

    return yol


if __name__ == "__main__":
    print("---- SAHA EKRANI BOT BASLIYOR ----")

    h = haberleri_cek()

    if h:
        ai_veri = ozgunlestir(h)

        resim = resim_olustur(
            ai_veri,
            h['gorsel']
        )

        aciklama = aciklama_kaydet(
            ai_veri
        )

        gecmiye_kaydet(
            h['baslik'],
            resim,
            aciklama
        )

        print("---- İŞLEM BİTTİ ----")
