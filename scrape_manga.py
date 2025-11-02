import requests, json, os, time, signal, sys
from bs4 import BeautifulSoup
from datetime import datetime
import re

# === KONFIGURASI ===
BASE_DIR = "comics"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://komikindo.ch/"}
DELAY_CHAPTER = 0.3
os.makedirs(BASE_DIR, exist_ok=True)

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# === SAVE ON STOP ===
def save_and_exit(sig=None, frame=None):
    print(f"\n[{now()}] Dihentikan oleh user (Ctrl+C)")
    print(f"[{now()}] SELESAI (aman)! Semua data tersimpan per file.")
    sys.exit(0)

signal.signal(signal.SIGINT, save_and_exit)

# === SANITIZE FILENAME: Ganti spasi → dash, hapus karakter terlarang ===
def sanitize_filename(name):
    # Ganti spasi dengan dash
    name = name.replace(" ", "-")
    # Hapus karakter tidak aman
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Hapus tanda titik di awal/akhir
    name = name.strip('.')
    # Batasi panjang
    return name[:100]

# === FUNGSI GET & SOUP ===
def get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"   Gagal: {e}")
        return None

def soup(url):
    html = get(url)
    return BeautifulSoup(html, 'html.parser') if html else None

# === SIMPAN KOMIK KE FILE SENDIRI ===
def save_comic(comic_data):
    title = comic_data['title']
    safe_title = sanitize_filename(title)
    filename = f"{BASE_DIR}/{safe_title}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(comic_data, f, ensure_ascii=False, indent=2)
    print(f"[{now()}]    Simpan: {filename} ({len(comic_data['chapters'])} chapter)")

# === LOAD DAFTAR FILE YANG SUDAH ADA (untuk skip) ===
existing_files = {
    os.path.splitext(f)[0].replace("-", " ") for f in os.listdir(BASE_DIR)
    if f.endswith('.json')
}

# === AMBIL DAFTAR KOMIK ===
print(f"[{now()}] Mengambil daftar komik...")
s = soup("https://komikindo.ch/komik-terbaru/")
comics = []
for a in s.select('.animepost a[itemprop="url"]'):
    if a.get('href'):
        title = a['title'].replace("Komik ", "", 1).strip()
        comics.append({"title": title, "url": a['href']})

# === LOOP SETIAP KOMIK ===
for comic in comics:
    title, url = comic['title'], comic['url']
    print(f"\n[{now()}] → {title}")

    if title in existing_files:
        print(f"[{now()}]    Sudah ada, skip.")
        continue

    # === BUAT DATA KOMIK ===
    comic_data = {
        "title": title,
        "cover_image": None,
        "alternative_titles": [], "status": "", "author": [], "illustrator": [],
        "type": "", "demographic": "", "themes": [], "genres": [],
        "rating": 0.0, "votes": 0, "synopsis": "", "last_updated": "", "chapters": []
    }

    # === DETAIL KOMIK ===
    s_detail = soup(url)
    if not s_detail:
        continue

    # Cover
    thumb = s_detail.find('div', class_='thumb')
    if thumb and thumb.find('img'):
        comic_data['cover_image'] = thumb.find('img')['src']

    # Info dari .infox
    infox = s_detail.find('div', class_='infox')
    if infox:
        for span in infox.find_all('span'):
            b = span.find('b')
            if not b: continue
            key = b.get_text(strip=True).rstrip(':').lower()
            text = span.get_text(separator=" ", strip=True)

            if "judul alternatif" in key:
                comic_data['alternative_titles'] = [x.strip() for x in text.split(":", 1)[1].split(",") if x.strip()]
            elif "status" in key:
                comic_data['status'] = text.split(":", 1)[1].strip()
            elif "pengarang" in key:
                comic_data['author'] = [x.strip() for x in text.split(":", 1)[1].split(",") if x.strip()]
            elif "ilustrator" in key:
                comic_data['illustrator'] = [x.strip() for x in text.split(":", 1)[1].split(",") if x.strip()]
            elif "grafis" in key:
                a = span.find('a')
                comic_data['demographic'] = a.get_text(strip=True) if a else ""
            elif "tema" in key:
                comic_data['themes'] = [a.get_text(strip=True) for a in span.find_all('a')]
            elif "jenis komik" in key:
                a = span.find('a')
                comic_data['type'] = a.get_text(strip=True) if a else ""

    # Genre
    genre_div = s_detail.find('div', class_='genre-info')
    if genre_div:
        comic_data['genres'] = [a.get_text(strip=True) for a in genre_div.find_all('a')]

    # Rating
    rt = s_detail.find('i', itemprop='ratingValue')
    comic_data['rating'] = float(rt.get_text(strip=True)) if rt else 0.0
    vt = s_detail.find('div', class_='votescount')
    comic_data['votes'] = int(''.join(filter(str.isdigit, vt.get_text(strip=True)))) if vt else 0

    # Sinopsis
    syn = s_detail.find('div', class_='entry-content-single')
    comic_data['synopsis'] = syn.get_text(separator=" ", strip=True) if syn else ""

    # Last updated
    date_span = s_detail.find('span', class_='datech')
    comic_data['last_updated'] = date_span.get_text(strip=True) if date_span else ""

    # === SEMUA CHAPTER ===
    ch_list = s_detail.find('div', id='chapter_list')
    if ch_list:
        for li in reversed(ch_list.find_all('li')):
            a = li.find('a')
            if not a: continue
            ch_tag = a.find('chapter')
            if not ch_tag: continue
            ch_num = ch_tag.get_text(strip=True)
            ch_url = a['href']

            print(f"[{now()}]    → Chapter {ch_num}")

            s_ch = soup(ch_url)
            if not s_ch: continue
            container = s_ch.find('div', id='Baca_Komik') or s_ch.find('div', class_='chapter-image')
            if not container: continue

            images = []
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src and src.startswith('http'):
                    images.append(src.strip())

            comic_data['chapters'].append({
                "number": ch_num,
                "images": images
            })

            # SIMPAN SETIAP CHAPTER SELESAI
            save_comic(comic_data)
            time.sleep(DELAY_CHAPTER)

    # SIMPAN AKHIR
    save_comic(comic_data)
    existing_files.add(title)

# === SELESAI ===
save_and_exit()