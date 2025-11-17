# scrape_komikindo_daftar_manga_FIXED.py
import requests, json, os, time, signal, sys, re
from bs4 import BeautifulSoup
from datetime import datetime

# === KONFIGURASI ===
BASE_DIR = "komikindo_daftar_manga"          # Folder hasil
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": "https://komikindo.ch/"
}
DELAY_PAGE = 1.8
DELAY_CHAPTER = 0.6
MAX_PAGES = 1
os.makedirs(BASE_DIR, exist_ok=True)

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# === SAVE ON CTRL+C ===
def save_and_exit(sig=None, frame=None):
    print(f"\n[{now()}] Scraping dihentikan (Ctrl+C)")
    print(f"[{now()}] Semua data aman tersimpan!")
    sys.exit(0)
signal.signal(signal.SIGINT, save_and_exit)

# === SANITIZE & CLEAN ===
def sanitize_filename(name):
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    name = name.replace(' ', '-')
    return name[:150]

def clean_title(title):
    return re.sub(r'^Komik\s+', '', title, flags=re.IGNORECASE).strip()

# === REQUEST ===
def get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        r.encoding = 'utf-8'
        return r.text
    except Exception as e:
        print(f"   [ERROR] Gagal akses {url[:60]}... → {e}")
        return None

def soup(url):
    html = get(url)
    return BeautifulSoup(html, 'html.parser') if html else None

# === SAVE COMIC ===
def save_comic(data):
    safe = sanitize_filename(data['title'])
    path = f"{BASE_DIR}/{safe}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[{now()}] Simpan → {safe}.json ({len(data.get('chapters',[]))} chapter)")

# === LOAD EXISTING (by URL) ===
def get_existing():
    existing = {}
    if not os.path.exists(BASE_DIR):
        return existing
    for f in os.listdir(BASE_DIR):
        if f.endswith('.json'):
            try:
                with open(os.path.join(BASE_DIR, f), 'r', encoding='utf-8') as file:
                    d = json.load(file)
                    if d.get('url'):
                        existing[d['url']] = d
            except: pass
    return existing

# === EXTRACT TITLE DARI LIST ===
def extract_title(a_tag):
    # Prioritas 1: dari teks judul (paling akurat)
    h4 = a_tag.find_parent('div', class_='animepost')
    if h4:
        txt = h4.select_one('.bigors .tt h4 a')
        if txt:
            return clean_title(txt.get_text(strip=True))
    # Prioritas 2: dari attribute title / alt
    for attr in ['title', 'alt']:
        val = a_tag.get(attr) or (a_tag.find('img') or {}).get(attr)
        if val:
            return clean_title(val)
    # Prioritas 3: dari URL
    m = re.search(r'/komik/([^/]+)/', a_tag.get('href', ''))
    if m:
        return clean_title(m.group(1).replace('-', ' ').title())
    return "Unknown"

# === EXTRACT INFO DETAIL ===
def extract_info(s_detail, url, list_title):
    info = {
        "title": list_title, "url": url, "cover_image": None,
        "alternative_titles": [], "status": "", "author": [], "type": "", "genres": [],
        "rating": 0.0, "synopsis": "", "last_updated": "", "scraped_at": now()
    }
    # Cover
    img = s_detail.select_one('.thumb img')
    if img: info['cover_image'] = img.get('src') or img.get('data-src')

    # Infox
    for span in s_detail.select('.infox span'):
        t = span.get_text(strip=True)
        if "Judul Alternatif:" in t:
            info['alternative_titles'] = [x.strip() for x in t.split(':')[1].split(',') if x]
        if "Status:" in t:
            info['status'] = t.split(':')[1].strip()
        if "Pengarang:" in t:
            info['author'] = [x.strip() for x in t.split(':')[1].split(',') if x]
        if "Jenis Komik:" in t:
            a = span.find('a')
            if a: info['type'] = a.get_text(strip=True)

    # Genre
    info['genres'] = [a.get_text(strip=True) for a in s_detail.select('.genre-info a, .genres a')]

    # Rating
    r = s_detail.select_one('i[itemprop="ratingValue"], .rtg i')
    if r:
        try: info['rating'] = float(r.get_text(strip=True))
        except: pass

    # Sinopsis
    syn = s_detail.select_one('.entry-content-single, .entry-content')
    if syn: info['synopsis'] = syn.get_text(separator='\n', strip=True)

    return info

# === EXTRACT CHAPTERS ===
def extract_chapters(s_detail):
    chapters = []
    cl = s_detail.find('div', id='chapter_list')
    if not cl: return chapters
    for li in cl.find_all('li'):
        a = li.find('a')
        if not a: continue
        txt = a.get_text(strip=True)
        m = re.search(r'Chapter\s*([\d\.]+)', txt, re.I)
        if not m: continue
        chapters.append({
            "number": f"Chapter {m.group(1)}",
            "url": a['href'],
            "date": li.select_one('.dt').get_text(strip=True) if li.select_one('.dt') else ""
        })
    return chapters

# === EXTRACT IMAGES CHAPTER ===
def extract_images(s_ch):
    imgs = []
    container = s_ch.find('div', id='Baca_Komik') or s_ch.select_one('.reader-area')
    if container:
        for img in container.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
            if src and src.startswith('http'):
                src = src.split('?')[0].strip()
                if src not in imgs:
                    imgs.append(src)
    return imgs

# === MAIN ===
if __name__ == "__main__":
    print(f"[{now()}] SCRAPING DAFTAR MANGA A-Z KOMIKINDO (FIXED SELECTOR)")
    existing = get_existing()
    print(f"[{now()}] Sudah ada {len(existing)} komik (akan di-skip)")

    page = 1
    all_comics = []

    # PHASE 1: Kumpulkan semua link komik (tanpa duplikat)
    while page <= MAX_PAGES:
        url = "https://komikindo.ch/daftar-manga/" if page == 1 else f"https://komikindo.ch/daftar-manga/page/{page}/"
        print(f"\n[{now()}] Halaman {page} → {url}")
        s = soup(url)
        if not s:
            print("   Gagal load halaman → coba lagi nanti")
            time.sleep(5)
            continue

        # FIXED SELECTOR: hilangkan '>' biar match nested link di .ply
        links = s.select('.animepost .limit a[itemprop="url"]')

        # DEBUG: Print jumlah links untuk verifikasi
        print(f"   DEBUG: Ditemukan {len(links)} link potensial")

        if not links:
            print("   Tidak ada lagi komik → selesai")
            break

        seen = set()
        for a in links:
            href = a.get('href')
            if not href or '/chapter-' in href or href in seen:
                continue
            seen.add(href)
            title = extract_title(a)
            if title and title != "Unknown":
                all_comics.append({"title": title, "url": href})
                print(f"   + {title}")

        # Cek next page
        if not s.select_one('a.next.page-numbers'):
            print(f"[{now()}] Halaman terakhir tercapai (halaman {page})")
            break

        page += 1
        time.sleep(DELAY_PAGE)

    print(f"\n[{now()}] Total unik ditemukan: {len(all_comics)} komik")

    # PHASE 2: Scraping detail & chapter
    for i, comic in enumerate(all_comics, 1):
        title, url = comic['title'], comic['url']
        print(f"\n[{now()}] [{i}/{len(all_comics)}] {title}")

        if url in existing:
            print("   Sudah ada → skip")
            continue

        s_detail = soup(url)
        if not s_detail:
            print("   Gagal buka detail → skip")
            continue

        data = extract_info(s_detail, url, title)
        data['chapters'] = []
        chapters = extract_chapters(s_detail)
        print(f"   {len(chapters)} chapter")

        for j, ch in enumerate(reversed(chapters), 1):
            print(f"   → {ch['number']} ({j}/{len(chapters)})")
            s_ch = soup(ch['url'])
            imgs = extract_images(s_ch) if s_ch else []
            data['chapters'].append({
                "number": ch['number'],
                "url": ch['url'],
                "date": ch['date'],
                "images": imgs
            })
            print(f"      {len(imgs)} gambar")
            time.sleep(DELAY_CHAPTER)

            if j % 10 == 0 or j == len(chapters):
                save_comic(data)

        save_comic(data)
        existing[url] = data

    print(f"\n[{now()}] SELESAI 100%! Folder: {os.path.abspath(BASE_DIR)}")