import requests, json, os, time, signal, sys, re
from bs4 import BeautifulSoup
from datetime import datetime

# === KONFIGURASI ===
BASE_DIR = "comics"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://komikindo.ch/"
}
DELAY_PAGE = 1.0
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

# === SANITIZE FILENAME ===
def sanitize_filename(name):
    name = name.replace(" ", "-")
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip('. ')[:100]

# === GET & SOUP ===
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

# === SIMPAN KOMIK ===
def save_comic(comic_data):
    title = comic_data['title']
    safe_title = sanitize_filename(title)
    filename = f"{BASE_DIR}/{safe_title}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(comic_data, f, ensure_ascii=False, indent=2)
    print(f"[{now()}]    Simpan: {filename} ({len(comic_data['chapters'])} chapter)")

# === LOAD KOMIK YANG SUDAH ADA ===
def load_existing_comic(title):
    safe_title = sanitize_filename(title)
    filepath = f"{BASE_DIR}/{safe_title}.json"
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"   Gagal baca file lama: {e}")
        return None

# === DAFTAR KOMIK YANG SUDAH ADA (untuk skip) ===
existing_titles = {
    os.path.splitext(f)[0].replace("-", " ") for f in os.listdir(BASE_DIR)
    if f.endswith('.json')
}

# === SCRAPING SEMUA HALAMAN ===
print(f"[{now()}] Mengambil daftar komik dari semua halaman...")
all_comics = []
page = 1

while True:
    url = f"https://komikindo.ch/komik-terbaru/page/{page}/" if page > 1 else "https://komikindo.ch/komik-terbaru/"
    print(f"[{now()}] Halaman {page}: {url}")
    
    s = soup(url)
    if not s:
        print(f"[{now()}] Gagal akses halaman {page}. Stop.")
        break

    posts = s.select('.animepost a[itemprop="url"]')
    if not posts:
        print(f"[{now()}] Tidak ada komik di halaman {page}. Selesai.")
        break

    for a in posts:
        if not a.get('href'): continue
        title = a['title'].replace("Komik ", "", 1).strip()
        all_comics.append({"title": title, "url": a['href']})

    # Cek halaman berikutnya
    next_btn = s.find('a', string=re.compile(r'Next|›'))
    if not next_btn or 'disabled' in next_btn.get('class', []):
        print(f"[{now()}] Halaman terakhir: {page}")
        break

    page += 1
    time.sleep(DELAY_PAGE)

print(f"[{now()}] Ditemukan {len(all_comics)} komik dari {page} halaman.")

# === LOOP SETIAP KOMIK ===
for idx, comic in enumerate(all_comics, 1):
    title, url = comic['title'], comic['url']
    print(f"\n[{now()}] [{idx}/{len(all_comics)}] → {title}")

    # === CEK APAKAH SUDAH ADA ===
    existing_data = load_existing_comic(title)
    
    if existing_data and existing_data.get('chapters'):
        print(f"[{now()}]    Sudah ada {len(existing_data['chapters'])} chapter. Cek update...")
        
        existing_chapters = {ch['number'] for ch in existing_data['chapters']}
        new_chapters = []

        # === AMBIL HALAMAN DETAIL ===
        s_detail = soup(url)
        if not s_detail:
            print(f"[{now()}]    Gagal akses detail. Skip update.")
            continue

        # Update last_updated dari chapter terbaru
        ch_list = s_detail.find('div', id='chapter_list')
        if ch_list:
            first_li = ch_list.find('li')
            if first_li:
                date_span = first_li.find('span', class_='datech')
                if date_span:
                    existing_data['last_updated'] = date_span.get_text(strip=True)

            # === CARI CHAPTER BARU ===
            for li in ch_list.find_all('li'):
                a = li.find('a')
                if not a: continue
                ch_tag = a.find('chapter')
                if not ch_tag: continue
                ch_num = ch_tag.get_text(strip=True)
                ch_url = a['href']

                if ch_num in existing_chapters:
                    continue  # sudah ada

                print(f"[{now()}]    → Chapter BARU: {ch_num}")
                s_ch = soup(ch_url)
                if not s_ch: 
                    print(f"[{now()}]       Gagal akses chapter")
                    continue

                container = s_ch.find('div', id='Baca_Komik') or s_ch.find('div', class_='chapter-image')
                if not container: 
                    print(f"[{now()}]       Tidak ada gambar")
                    continue

                images = []
                for img in container.find_all('img'):
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src and src.startswith('http'):
                        images.append(src.strip())

                new_chapters.append({
                    "number": ch_num,
                    "images": images
                })
                time.sleep(DELAY_CHAPTER)

        # === TAMBAHKAN CHAPTER BARU ===
        if new_chapters:
            existing_data['chapters'].extend(new_chapters)
            # Urutkan chapter dari 01 ke terbaru
            existing_data['chapters'].sort(key=lambda x: int(re.sub(r'\D', '', x['number']) or 0))
            save_comic(existing_data)
            print(f"[{now()}]    Update selesai: +{len(new_chapters)} chapter baru.")
        else:
            print(f"[{now()}]    Tidak ada chapter baru.")
        continue

    # === KOMIK BARU: SCRAPING LENGKAP ===
    print(f"[{now()}]    Komik baru, mulai scraping...")
    comic_data = {
        "title": title,
        "cover_image": None,
        "alternative_titles": [], "status": "", "author": [], "illustrator": [],
        "type": "", "demographic": "", "themes": [], "genres": [],
        "rating": 0.0, "votes": 0, "synopsis": "", "last_updated": "", "chapters": []
    }

    s_detail = soup(url)
    if not s_detail:
        print(f"[{now()}]    Gagal akses detail. Skip.")
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
    comic_data['last_updated'] = date_span.get_text(strip=True) if date_span else now().split()[0]

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

            save_comic(comic_data)
            time.sleep(DELAY_CHAPTER)

    save_comic(comic_data)
    existing_titles.add(title)

# === SELESAI ===
save_and_exit()