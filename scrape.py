import requests, json, os, time, signal, sys, re, random
from bs4 import BeautifulSoup
from datetime import datetime

# === KONFIGURASI ===
BASE_DIR = "comics"

# ROTATING USER AGENTS
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Referer": "https://komikindo.ch/",
        "DNT": "1",
        "Connection": "keep-alive",
    }

# DELAY OPTIMIZED UNTUK GITHUB ACTIONS
DELAY_PAGE = 2.0
DELAY_CHAPTER = 1.5
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
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    name = name.replace(' ', '-')
    return name[:100]

# === CLEAN TITLE ===
def clean_title(title):
    title = re.sub(r'^Komik\s+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

# === SAFE CHAPTER SORTING ===
def safe_chapter_sort(chapters):
    def get_chapter_num(ch):
        num_str = ch['number']
        try:
            cleaned = re.sub(r'[^\d.]', '', num_str)
            while '..' in cleaned:
                cleaned = cleaned.replace('..', '.')
            cleaned = cleaned.strip('.')
            if cleaned and cleaned != '.':
                return float(cleaned)
            return 0
        except (ValueError, AttributeError):
            return 0
    
    chapters.sort(key=get_chapter_num)
    return chapters

# === IMPROVED GET & SOUP ===
def get_with_retry(url, max_retries=2):
    for attempt in range(max_retries):
        try:
            headers = get_headers()
            print(f"   Attempt {attempt + 1}: Mengakses {url}")
            
            session = requests.Session()
            session.headers.update(headers)
            
            r = session.get(url, timeout=25)
            r.encoding = 'utf-8'
            
            if r.status_code == 200:
                if "komik" in r.text.lower() or "chapter" in r.text.lower():
                    print(f"   ✅ Success mendapatkan konten")
                    return r.text
                else:
                    print(f"   ⚠️  Dapat response tapi konten tidak expected")
            else:
                print(f"   ❌ Status {r.status_code}")
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                print(f"   403 Forbidden - Attempt {attempt + 1}")
            elif e.response.status_code == 429:
                print(f"   429 Too Many Requests")
                time.sleep(10)
            else:
                print(f"   HTTP Error: {e}")
        except requests.exceptions.RequestException as e:
            print(f"   Request Error: {e}")
        
        if attempt < max_retries - 1:
            retry_delay = random.uniform(5, 15)
            print(f"   Waiting {retry_delay:.1f}s sebelum retry...")
            time.sleep(retry_delay)
    
    return None

def get(url):
    return get_with_retry(url)

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
    print(f"[{now()}]    💾 Simpan: {filename} ({len(comic_data['chapters'])} chapter)")

# === SIMPAN SEMUA KOMIK SEKALIGUS (OPTIMIZED UNTUK GITHUB ACTIONS) ===
def save_all_comics(comics_data):
    """Simpan semua komik sekaligus - optimized untuk GitHub Actions"""
    print(f"[{now()}] 💾 Menyimpan semua {len(comics_data)} komik sekaligus...")
    
    total_chapters = 0
    for comic_data in comics_data:
        title = comic_data['title']
        safe_title = sanitize_filename(title)
        filename = f"{BASE_DIR}/{safe_title}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(comic_data, f, ensure_ascii=False, indent=2)
        
        total_chapters += len(comic_data.get('chapters', []))
        print(f"[{now()}]    ✅ {safe_title}.json ({len(comic_data['chapters'])} chapter)")
    
    print(f"[{now()}] 📊 Total: {len(comics_data)} komik, {total_chapters} chapter tersimpan")

# === LOAD KOMIK YANG SUDAH ADA ===
def load_existing_comic(url):
    if not os.path.exists(BASE_DIR):
        return None
        
    for f in os.listdir(BASE_DIR):
        if f.endswith('.json'):
            filepath = os.path.join(BASE_DIR, f)
            try:
                with open(filepath, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    if data.get('url') == url:
                        return data
            except Exception as e:
                print(f"   Warning: Gagal baca {filepath}: {e}")
    return None

# === GET ALL EXISTING COMICS ===
def get_all_existing_comics():
    existing = {}
    if not os.path.exists(BASE_DIR):
        return existing
        
    for f in os.listdir(BASE_DIR):
        if f.endswith('.json'):
            filepath = os.path.join(BASE_DIR, f)
            try:
                with open(filepath, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    url = data.get('url')
                    if url:
                        existing[url] = data
            except Exception as e:
                print(f"   Warning: Gagal baca {filepath}: {e}")
    return existing

# === EXTRACT COMIC INFO ===
def extract_comic_info(s_detail, url, list_title):
    info = {
        "title": list_title,
        "cover_image": None,
        "alternative_titles": [],
        "status": "",
        "author": [],
        "illustrator": [],
        "type": "",
        "demographic": "",
        "themes": [],
        "genres": [],
        "rating": 0.0,
        "votes": 0,
        "synopsis": "",
        "last_updated": "",
        "url": url,
        "scraped_at": now()
    }
    
    # COVER
    thumb = s_detail.find('div', class_='thumb')
    if thumb and thumb.find('img'):
        info['cover_image'] = thumb.find('img')['src']
    
    # INFO
    infox = s_detail.find('div', class_='infox')
    if infox:
        for span in infox.find_all('span'):
            text = span.get_text(strip=True)
            
            if "Judul Alternatif:" in text:
                alt_text = text.replace("Judul Alternatif:", "").strip()
                info['alternative_titles'] = [x.strip() for x in alt_text.split(",") if x.strip()]
            elif "Status:" in text:
                info['status'] = text.replace("Status:", "").strip()
            elif "Pengarang:" in text:
                author_text = text.replace("Pengarang:", "").strip()
                info['author'] = [x.strip() for x in author_text.split(",") if x.strip()]
            elif "Ilustrator:" in text:
                illus_text = text.replace("Ilustrator:", "").strip()
                info['illustrator'] = [x.strip() for x in illus_text.split(",") if x.strip()]
            elif "Grafis:" in text:
                a = span.find('a')
                if a:
                    info['demographic'] = a.get_text(strip=True)
            elif "Tema:" in text:
                info['themes'] = [a.get_text(strip=True) for a in span.find_all('a')]
            elif "Jenis Komik:" in text:
                a = span.find('a')
                if a:
                    info['type'] = a.get_text(strip=True)
    
    # GENRE
    genre_elements = s_detail.select('.genre-info a, .series-genres a, .genres a')
    if genre_elements:
        info['genres'] = [a.get_text(strip=True) for a in genre_elements if a.get_text(strip=True)]
    
    # RATING
    rating_selectors = [
        'i[itemprop="ratingValue"]',
        '.ratingmanga i',
        '.rtg i',
        '.archiveanime-rating i'
    ]
    
    for selector in rating_selectors:
        rating_elem = s_detail.select_one(selector)
        if rating_elem:
            try:
                rating_text = rating_elem.get_text(strip=True)
                rating_match = re.search(r'(\d+\.\d+|\d+)', rating_text)
                if rating_match:
                    info['rating'] = float(rating_match.group(1))
                    break
            except (ValueError, AttributeError):
                continue
    
    # SINOPSIS
    synopsis_selectors = [
        '.entry-content.entry-content-single',
        '.entry-content-single',
        '.synopsis',
        '.description'
    ]
    
    for selector in synopsis_selectors:
        synopsis_elem = s_detail.select_one(selector)
        if synopsis_elem:
            synopsis_text = synopsis_elem.get_text(separator='\n', strip=True)
            lines = synopsis_text.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and not re.match(r'^(Manhua|Manga|Manhwa)\s+', line, re.IGNORECASE):
                    cleaned_lines.append(line)
            
            if cleaned_lines:
                info['synopsis'] = '\n'.join(cleaned_lines)
                break
    
    # LAST UPDATED
    last_update = s_detail.find('span', class_='datech')
    if last_update:
        info['last_updated'] = last_update.get_text(strip=True)
    
    return info

# === EXTRACT CHAPTERS ===
def extract_chapters(s_detail):
    chapters = []
    
    chapter_list = s_detail.find('div', id='chapter_list')
    if chapter_list:
        for li in chapter_list.find_all('li'):
            lchx = li.find('span', class_='lchx')
            if lchx:
                a = lchx.find('a')
                if a and a.find('chapter'):
                    ch_num = a.find('chapter').get_text(strip=True)
                    ch_url = a['href']
                    
                    date_span = li.find('span', class_='dt')
                    ch_date = date_span.get_text(strip=True) if date_span else ""
                    
                    chapters.append({
                        "number": ch_num,
                        "url": ch_url,
                        "date": ch_date,
                        "images": []
                    })
    
    return chapters

# === EXTRACT CHAPTER IMAGES ===
def extract_chapter_images(soup_obj):
    images = []
    
    containers = [
        soup_obj.find('div', id='Baca_Komik'),
        soup_obj.find('div', class_='chapter-image'),
        soup_obj.select_one('.reader-area'),
        soup_obj.select_one('.chapter-body')
    ]
    
    for container in containers:
        if container:
            for img in container.find_all('img'):
                src = (img.get('src') or 
                       img.get('data-src') or 
                       img.get('data-lazy-src') or
                       img.get('data-original'))
                
                if src and src.startswith(('http://', 'https://')):
                    src = src.split('?')[0].strip()
                    if src not in images:
                        images.append(src)
            
            if images:
                break
    
    return images

# === TAMPILKAN INFO KOMIK ===
def display_comic_info(comic_data):
    print(f"\n📖 INFO KOMIK:")
    print(f"   Judul: {comic_data.get('title', 'N/A')}")
    print(f"   Status: {comic_data.get('status', 'N/A')}")
    print(f"   Tipe: {comic_data.get('type', 'N/A')}")
    print(f"   Rating: {comic_data.get('rating', 0.0)}/10 ({comic_data.get('votes', 0)} votes)")
    print(f"   Genre: {', '.join(comic_data.get('genres', []))}")
    print(f"   Update Terakhir: {comic_data.get('last_updated', 'N/A')}")
    
    synopsis = comic_data.get('synopsis', '')
    if synopsis:
        if len(synopsis) > 200:
            synopsis = synopsis[:200] + "..."
        print(f"   Sinopsis: {synopsis}")
    
    print(f"   Total Chapter: {len(comic_data.get('chapters', []))}")

# === EXTRACT TITLE FROM LIST PAGE ===
def extract_title_from_list(a_element):
    try:
        animepost_parent = a_element.find_parent('.animepost')
        if animepost_parent:
            title_elem = animepost_parent.select_one('.bigors .tt h4 a')
            if title_elem:
                title = title_elem.get_text(strip=True)
                title = clean_title(title)
                if title:
                    return title
    except Exception as e:
        print(f"      Warning: Gagal extract title dari .tt h4 a: {e}")
    
    title = a_element.get('title', '')
    if title:
        title = clean_title(title)
        if title:
            return title
    
    img = a_element.find('img')
    if img and img.get('alt'):
        title = img.get('alt')
        title = clean_title(title)
        if title:
            return title
    
    href = a_element.get('href', '')
    if href and '/komik/' in href:
        match = re.search(r'/komik/([^/]+)/', href)
        if match:
            title_from_url = match.group(1).replace('-', ' ').title()
            title_from_url = clean_title(title_from_url)
            return title_from_url
    
    return "Unknown-Title"

# === FILTER KOMIK VS CHAPTER ===
def is_comic_url(url):
    if not url:
        return False
    
    if re.search(r'-chapter-\d+', url) or re.search(r'/chapter-\d+', url):
        return False
    
    if '/komik/' in url and not re.search(r'-chapter-\d+', url):
        return True
    
    return False

# === MOCK DATA FOR TESTING ===
def create_mock_data():
    """Create mock data ketika website tidak bisa diakses"""
    print(f"[{now()}] 🎭 Creating mock data untuk testing...")
    
    mock_comics = [
        {
            "title": "Demo Comic 1",
            "status": "Ongoing",
            "type": "Manga", 
            "genres": ["Action", "Adventure"],
            "rating": 8.5,
            "synopsis": "Ini adalah data demo untuk testing.",
            "last_updated": now(),
            "chapters": [
                {
                    "number": "1",
                    "url": "https://example.com/chapter1",
                    "date": "2024-01-01",
                    "images": []
                }
            ],
            "note": "Mock data - Website tidak dapat diakses"
        },
        {
            "title": "Demo Comic 2", 
            "status": "Completed",
            "type": "Manhwa",
            "genres": ["Romance", "Drama"],
            "rating": 7.8,
            "synopsis": "Data demo kedua untuk testing workflow.",
            "last_updated": now(),
            "chapters": [
                {
                    "number": "1",
                    "url": "https://example.com/chapter1",
                    "date": "2024-01-01", 
                    "images": []
                }
            ],
            "note": "Mock data - GitHub Actions IP diblokir"
        }
    ]
    
    save_all_comics(mock_comics)
    
    # Create info file
    info_data = {
        "last_updated": now(),
        "status": "mock_data",
        "total_comics": len(mock_comics),
        "message": "Data asli tidak dapat diakses dari GitHub Actions",
        "next_check": "6 hours"
    }
    
    with open(f"{BASE_DIR}/INFO.json", 'w', encoding='utf-8') as f:
        json.dump(info_data, f, ensure_ascii=False, indent=2)
    
    return len(mock_comics)

# === MAIN SCRIPT ===
if __name__ == "__main__":
    print(f"[{now()}] 🚀 Memulai scraping komik dari KomikIndo...")
    print(f"[{now()}] ⚡ Running on GitHub Actions - OPTIMIZED MODE")
    print(f"[{now()}] 💾 Save Strategy: Simpan semua data sekaligus di akhir")
    
    # Test koneksi dulu
    print(f"[{now()}] 🔍 Testing koneksi ke website...")
    test_url = "https://komikindo.ch/komik-terbaru/"
    
    try:
        headers = get_headers()
        test_response = requests.get(test_url, headers=headers, timeout=15)
        
        if test_response.status_code == 200:
            print(f"[{now()}] ✅ Website dapat diakses, melanjutkan scraping...")
            USE_MOCK_DATA = False
        else:
            print(f"[{now()}] ❌ Website returned status: {test_response.status_code}")
            USE_MOCK_DATA = True
            
    except Exception as e:
        print(f"[{now()}] ❌ Tidak dapat mengakses website: {e}")
        print(f"[{now()}] 💡 GitHub Actions IP mungkin diblokir")
        USE_MOCK_DATA = True
    
    if USE_MOCK_DATA:
        print(f"[{now()}] 🎭 Menggunakan mock data untuk testing...")
        comic_count = create_mock_data()
        print(f"[{now()}] ✅ Berhasil membuat {comic_count} mock comics")
        print(f"[{now()}] 📁 Data disimpan di folder 'comics/'")
        sys.exit(0)
    
    # === NORMAL SCRAPING JIKA BISA AKSES ===
    print(f"[{now()}] Fitur: Title dari halaman list, Sinopsis, Genre, Rating")
    
    # Load existing comics
    existing_comics = get_all_existing_comics()
    print(f"[{now()}] Loaded {len(existing_comics)} existing comics")
    
    # === SCRAPING SEMUA HALAMAN ===
    print(f"[{now()}] Mengambil daftar komik dari semua halaman...")
    all_comics = []
    page = 1
    MAX_PAGES = 2  # Optimized untuk GitHub Actions

    while page <= MAX_PAGES:
        url = f"https://komikindo.ch/komik-terbaru/page/{page}/" if page > 1 else "https://komikindo.ch/komik-terbaru/"
        print(f"[{now()}] Halaman {page}: {url}")
        
        s = soup(url)
        if not s:
            print(f"[{now()}] Gagal akses halaman {page}. Skip halaman ini.")
            page += 1
            continue

        posts = (s.select('.listupd .animepost .animposx a[itemprop="url"]') or 
                 s.select('.animepost a[itemprop="url"]') or
                 s.select('.animepost .thumb a') or
                 s.select('.film-list a[itemprop="url"]'))

        if not posts:
            print(f"[{now()}] Tidak ada komik di halaman {page}. Selesai.")
            break

        comic_count = 0
        for a in posts:
            if not a.get('href'): 
                continue
            
            comic_url = a['href']
            
            if not is_comic_url(comic_url):
                continue
                
            title = extract_title_from_list(a)
            
            if title and title not in [c['title'] for c in all_comics]:
                all_comics.append({
                    "title": title, 
                    "url": comic_url,
                    "scraped_at": now()
                })
                comic_count += 1
                print(f"[{now()}]      ✅ Found: {title}")

        print(f"[{now()}]      📊 Halaman {page}: {comic_count} komik ditemukan")

        next_btn = s.select_one('a.next.page-numbers')
        if not next_btn:
            print(f"[{now()}] Tidak ditemukan tombol next. Selesai di halaman {page}")
            break
            
        page += 1
        time.sleep(DELAY_PAGE + random.uniform(0.5, 1.5))

    print(f"[{now()}] 📈 Ditemukan {len(all_comics)} komik dari {page-1} halaman.")

    # Jika tidak ada komik yang ditemukan, buat mock data
    if not all_comics:
        print(f"[{now()}] ❌ Tidak ada komik yang berhasil di-scrape")
        print(f"[{now()}] 🎭 Fallback ke mock data...")
        comic_count = create_mock_data()
        print(f"[{now()}] ✅ Berhasil membuat {comic_count} mock comics")
        sys.exit(0)

    # === LOOP SETIAP KOMIK - OPTIMIZED UNTUK GITHUB ACTIONS ===
    print(f"[{now()}] 🚀 Memproses {len(all_comics)} komik (optimized mode)...")
    
    updated_comics = []
    processed_count = 0
    
    for idx, comic in enumerate(all_comics, 1):
        title, url = comic['title'], comic['url']
        print(f"\n[{now()}] [{idx}/{len(all_comics)}] 🎯 → {title}")
        
        if not url or not url.startswith('http'):
            print(f"[{now()}]    ❌ URL tidak valid: {url}")
            continue
        
        existing_data = existing_comics.get(url)
        
        if existing_data:
            print(f"[{now()}]    🔄 Sudah ada {len(existing_data.get('chapters', []))} chapter. Cek update...")
            
            if existing_data.get('title') != title:
                print(f"[{now()}]    ✏️ Update title: '{existing_data['title']}' → '{title}'")
                existing_data['title'] = title
            
            display_comic_info(existing_data)
            
            existing_chapters = {ch['number'] for ch in existing_data.get('chapters', [])}
            new_chapters = []

            # Ambil halaman detail untuk update
            s_detail = soup(url)
            if not s_detail:
                print(f"[{now()}]    ❌ Gagal akses detail. Skip update.")
                updated_comics.append(existing_data)
                continue

            # Update last_updated dari chapter terbaru
            last_update = s_detail.find('span', class_='datech')
            if last_update:
                existing_data['last_updated'] = last_update.get_text(strip=True)

            # Cari chapter baru
            chapters_data = extract_chapters(s_detail)
            for chapter in chapters_data:
                if chapter['number'] not in existing_chapters:
                    print(f"[{now()}]    → 🆕 Chapter BARU: {chapter['number']}")
                    
                    s_ch = soup(chapter['url'])
                    if not s_ch:
                        print(f"[{now()}]       ❌ Gagal akses chapter")
                        continue
                        
                    images = extract_chapter_images(s_ch)
                    print(f"[{now()}]       🖼️ Found {len(images)} images")
                    
                    new_chapters.append({
                        "number": chapter['number'],
                        "url": chapter['url'],
                        "date": chapter['date'],
                        "images": images
                    })
                    
                    time.sleep(DELAY_CHAPTER)

            # Tambahkan chapter baru
            if new_chapters:
                existing_data['chapters'].extend(new_chapters)
                existing_data['chapters'] = safe_chapter_sort(existing_data['chapters'])
                print(f"[{now()}]    ✅ Update selesai: +{len(new_chapters)} chapter baru.")
            else:
                print(f"[{now()}]    ℹ️ Tidak ada chapter baru.")
            
            updated_comics.append(existing_data)
            processed_count += 1
            continue

        # === KOMIK BARU: SCRAPING LENGKAP ===
        print(f"[{now()}]    🆕 Komik baru, mulai scraping...")
        
        s_detail = soup(url)
        if not s_detail:
            print(f"[{now()}]    ❌ Gagal akses detail. Skip.")
            continue

        # Extract comic info - GUNAKAN TITLE DARI LIST
        comic_data = extract_comic_info(s_detail, url, title)
        comic_data['chapters'] = []

        display_comic_info(comic_data)

        # Extract semua chapter
        chapters_data = extract_chapters(s_detail)
        print(f"[{now()}]    📚 Ditemukan {len(chapters_data)} chapter")

        # Scraping images untuk setiap chapter
        chapter_count = 0
        total_chapters = len(chapters_data)
        
        for chapter in reversed(chapters_data):
            ch_num, ch_url = chapter['number'], chapter['url']
            print(f"[{now()}]    → 📖 Chapter {ch_num} ({chapter_count + 1}/{total_chapters})")

            s_ch = soup(ch_url)
            if not s_ch: 
                print(f"[{now()}]       ❌ Gagal akses chapter")
                continue
            
            images = extract_chapter_images(s_ch)
            print(f"[{now()}]       🖼️ Found {len(images)} images")
            
            comic_data['chapters'].append({
                "number": ch_num,
                "url": ch_url,
                "date": chapter['date'],
                "images": images
            })
            
            chapter_count += 1
            time.sleep(DELAY_CHAPTER)

        # Sort chapters
        comic_data['chapters'] = safe_chapter_sort(comic_data['chapters'])
        updated_comics.append(comic_data)
        processed_count += 1
        print(f"[{now()}]    ✅ Selesai: {chapter_count} chapter tersimpan")

    # === SIMPAN SEMUA DATA SEKALIGUS DI AKHIR ===
    print(f"\n[{now()}] 💾 Menyimpan semua {len(updated_comics)} komik sekaligus...")
    save_all_comics(updated_comics)

    # === SELESAI ===
    print(f"\n[{now()}] 🎉 SEMUA KOMIK SELESAI DIPROSES!")
    print(f"[{now()}] 📊 Total komik: {len(updated_comics)}")
    
    total_chapters = sum(len(comic.get('chapters', [])) for comic in updated_comics)
    total_images = sum(len(chapter.get('images', [])) for comic in updated_comics for chapter in comic.get('chapters', []))
    
    print(f"[{now()}] 📚 Total chapter: {total_chapters}")
    print(f"[{now()}] 🖼️ Total images: {total_images}")
    print(f"[{now()}] ⏰ Waktu selesai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    save_and_exit()