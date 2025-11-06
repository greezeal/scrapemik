import requests, json, os, time, signal, sys, re
from bs4 import BeautifulSoup
from datetime import datetime

# === KONFIGURASI ===
BASE_DIR = "comics"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://komikindo.ch/"
}
DELAY_PAGE = 1.0
DELAY_CHAPTER = 0.5
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
    # Normalize dan bersihkan nama
    name = re.sub(r'\s+', ' ', name)  # Normalize spaces
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    # Ganti spasi dengan dash untuk penamaan file
    name = name.replace(' ', '-')
    return name[:100]

# === CLEAN TITLE ===
def clean_title(title):
    """Bersihkan title dari kata 'Komik' dan whitespace berlebihan"""
    # Hapus kata 'Komik' di awal
    title = re.sub(r'^Komik\s+', '', title, flags=re.IGNORECASE)
    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

# === GET & SOUP ===
def get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
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
def load_existing_comic(url):
    """Load existing comic by URL (more reliable than title)"""
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
    """Get all existing comics indexed by URL"""
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
    """Extract comic information from detail page - GUNAKAN TITLE DARI LIST"""
    info = {
        "title": list_title,  # GUNAKAN TITLE DARI HALAMAN LIST
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
    
    # COVER: Tetap ambil dari halaman detail
    thumb = s_detail.find('div', class_='thumb')
    if thumb and thumb.find('img'):
        info['cover_image'] = thumb.find('img')['src']
    
    # INFO: Tetap ambil dari .infox di halaman detail
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
    
    # GENRE: Tetap ambil dari halaman detail
    genre_elements = s_detail.select('.genre-info a, .series-genres a, .genres a')
    if genre_elements:
        info['genres'] = [a.get_text(strip=True) for a in genre_elements if a.get_text(strip=True)]
    
    # RATING: Tetap ambil dari halaman detail
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
    
    # VOTES: Tetap ambil dari halaman detail
    votes_selectors = [
        '.votescount',
        '.rating-count',
        '.vote-count'
    ]
    
    for selector in votes_selectors:
        votes_elem = s_detail.select_one(selector)
        if votes_elem:
            votes_text = votes_elem.get_text(strip=True)
            numbers = re.findall(r'\d+', votes_text)
            if numbers:
                info['votes'] = int(numbers[0])
                break
    
    # SINOPSIS: Tetap ambil dari halaman detail
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
            # Hapus bagian yang tidak perlu
            lines = synopsis_text.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and not re.match(r'^(Manhua|Manga|Manhwa)\s+', line, re.IGNORECASE):
                    cleaned_lines.append(line)
            
            if cleaned_lines:
                info['synopsis'] = '\n'.join(cleaned_lines)
                break
    
    # LAST UPDATED: Tetap ambil dari halaman detail
    last_update = s_detail.find('span', class_='datech')
    if last_update:
        info['last_updated'] = last_update.get_text(strip=True)
    
    return info

# === EXTRACT CHAPTERS ===
def extract_chapters(s_detail):
    """Extract chapters from detail page"""
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
                    
                    # Get date
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
    """Extract images from chapter page"""
    images = []
    
    # Multiple container selectors
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
                    # Clean URL
                    src = src.split('?')[0].strip()
                    if src not in images:
                        images.append(src)
            
            if images:
                break
    
    return images

# === TAMPILKAN INFO KOMIK ===
def display_comic_info(comic_data):
    """Display comic information in a formatted way"""
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
    """
    Extract title dari halaman list/update - DIPERBAIKI
    Ambil dari .tt h4 a seperti yang diminta
    """
    # METHOD 1: Ambil dari .tt h4 a (STRUKTUR YANG DIMINTA)
    try:
        animepost_parent = a_element.find_parent('.animepost')
        if animepost_parent:
            # Ambil dari struktur: .bigors .tt h4 a
            title_elem = animepost_parent.select_one('.bigors .tt h4 a')
            if title_elem:
                title = title_elem.get_text(strip=True)
                # Bersihkan title
                title = clean_title(title)
                if title:
                    return title
    except Exception as e:
        print(f"      Warning: Gagal extract title dari .tt h4 a: {e}")
    
    # METHOD 2: Fallback - dari attribute title
    title = a_element.get('title', '')
    if title:
        title = clean_title(title)
        if title:
            return title
    
    # METHOD 3: Fallback - dari alt image
    img = a_element.find('img')
    if img and img.get('alt'):
        title = img.get('alt')
        title = clean_title(title)
        if title:
            return title
    
    # METHOD 4: Fallback - dari URL
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
    """Filter untuk membedakan URL komik dengan URL chapter"""
    if not url:
        return False
    
    # URL chapter biasanya mengandung pattern '-chapter-' atau angka di akhir
    if re.search(r'-chapter-\d+', url) or re.search(r'/chapter-\d+', url):
        return False
    
    # URL komik biasanya mengandung '/komik/' dan tidak mengandung '-chapter-'
    if '/komik/' in url and not re.search(r'-chapter-\d+', url):
        return True
    
    return False

# === MAIN SCRIPT ===
if __name__ == "__main__":
    print(f"[{now()}] Memulai scraping komik dari KomikIndo...")
    print(f"[{now()}] Fitur: Title dari halaman list, Sinopsis, Genre, Rating")
    
    # Load existing comics
    existing_comics = get_all_existing_comics()
    print(f"[{now()}] Loaded {len(existing_comics)} existing comics")
    
    # === SCRAPING SEMUA HALAMAN ===
    print(f"[{now()}] Mengambil daftar komik dari semua halaman...")
    all_comics = []
    page = 1
    MAX_PAGES = 50  # Safety limit

    while page <= MAX_PAGES:
        url = f"https://komikindo.ch/komik-terbaru/page/{page}/" if page > 1 else "https://komikindo.ch/komik-terbaru/"
        print(f"[{now()}] Halaman {page}: {url}")
        
        s = soup(url)
        if not s:
            print(f"[{now()}] Gagal akses halaman {page}. Coba lagi...")
            time.sleep(DELAY_PAGE * 2)
            continue

        # Multiple selector fallbacks untuk list komik
        posts = (s.select('.listupd .animepost .animposx a[itemprop="url"]') or 
                 s.select('.animepost a[itemprop="url"]') or
                 s.select('.animepost .thumb a') or
                 s.select('.film-list a[itemprop="url"]'))

        if not posts:
            print(f"[{now()}] Tidak ada komik di halaman {page}. Selesai.")
            break

        for a in posts:
            if not a.get('href'): 
                continue
            
            comic_url = a['href']
            
            # FILTER PENTING: Hanya proses URL komik, bukan URL chapter
            if not is_comic_url(comic_url):
                continue
                
            # Extract title dari halaman list (STRATEGI UTAMA)
            title = extract_title_from_list(a)
            
            if title and title not in [c['title'] for c in all_comics]:
                all_comics.append({
                    "title": title, 
                    "url": comic_url,
                    "scraped_at": now()
                })
                print(f"[{now()}]      Found: {title}")

        # Next page detection
        next_btn = s.select_one('a.next.page-numbers')
        if not next_btn:
            print(f"[{now()}] Tidak ditemukan tombol next. Selesai di halaman {page}")
            break
            
        page += 1
        time.sleep(DELAY_PAGE)

    print(f"[{now()}] Ditemukan {len(all_comics)} komik dari {page} halaman.")

    # === LOOP SETIAP KOMIK ===
    for idx, comic in enumerate(all_comics, 1):
        title, url = comic['title'], comic['url']
        print(f"\n[{now()}] [{idx}/{len(all_comics)}] → {title}")
        
        # Skip jika URL tidak valid
        if not url or not url.startswith('http'):
            print(f"[{now()}]    URL tidak valid: {url}")
            continue
        
        # Cek existing berdasarkan URL (lebih reliable)
        existing_data = existing_comics.get(url)
        
        if existing_data:
            print(f"[{now()}]    Sudah ada {len(existing_data.get('chapters', []))} chapter. Cek update...")
            
            # Update title dengan title dari list (jika berbeda)
            if existing_data.get('title') != title:
                print(f"[{now()}]    Update title: '{existing_data['title']}' → '{title}'")
                existing_data['title'] = title
            
            # Tampilkan info komik yang sudah ada
            display_comic_info(existing_data)
            
            existing_chapters = {ch['number'] for ch in existing_data.get('chapters', [])}
            new_chapters = []

            # Ambil halaman detail untuk update
            s_detail = soup(url)
            if not s_detail:
                print(f"[{now()}]    Gagal akses detail. Skip update.")
                continue

            # Update last_updated dari chapter terbaru
            last_update = s_detail.find('span', class_='datech')
            if last_update:
                existing_data['last_updated'] = last_update.get_text(strip=True)

            # Cari chapter baru
            chapters_data = extract_chapters(s_detail)
            for chapter in chapters_data:
                if chapter['number'] not in existing_chapters:
                    print(f"[{now()}]    → Chapter BARU: {chapter['number']}")
                    
                    s_ch = soup(chapter['url'])
                    if not s_ch:
                        print(f"[{now()}]       Gagal akses chapter")
                        continue
                        
                    images = extract_chapter_images(s_ch)
                    print(f"[{now()}]       Found {len(images)} images")
                    
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
                # Urutkan chapter secara numeric
                existing_data['chapters'].sort(key=lambda x: 
                    float(re.search(r'[\d.]+', x['number']).group()) if re.search(r'[\d.]+', x['number']) else 0)
                save_comic(existing_data)
                print(f"[{now()}]    Update selesai: +{len(new_chapters)} chapter baru.")
            else:
                print(f"[{now()}]    Tidak ada chapter baru.")
            continue

        # === KOMIK BARU: SCRAPING LENGKAP ===
        print(f"[{now()}]    Komik baru, mulai scraping...")
        
        s_detail = soup(url)
        if not s_detail:
            print(f"[{now()}]    Gagal akses detail. Skip.")
            continue

        # Extract comic info - GUNAKAN TITLE DARI LIST
        comic_data = extract_comic_info(s_detail, url, title)
        comic_data['chapters'] = []

        # Tampilkan info komik yang baru di-scrape
        display_comic_info(comic_data)

        # Extract semua chapter
        chapters_data = extract_chapters(s_detail)
        print(f"[{now()}]    Ditemukan {len(chapters_data)} chapter")

        # Scraping images untuk setiap chapter (dari chapter 1 ke terbaru)
        chapter_count = 0
        total_chapters = len(chapters_data)
        
        for chapter in reversed(chapters_data):  # dari chapter 1 ke terbaru
            ch_num, ch_url = chapter['number'], chapter['url']
            print(f"[{now()}]    → Chapter {ch_num} ({chapter_count + 1}/{total_chapters})")

            s_ch = soup(ch_url)
            if not s_ch: 
                print(f"[{now()}]       Gagal akses chapter")
                continue
            
            images = extract_chapter_images(s_ch)
            print(f"[{now()}]       Found {len(images)} images")
            
            comic_data['chapters'].append({
                "number": ch_num,
                "url": ch_url,
                "date": chapter['date'],
                "images": images
            })
            
            chapter_count += 1
            
            # Untuk komik baru, simpan setiap 10 chapter atau di akhir
            if chapter_count % 10 == 0 or chapter_count == total_chapters:
                save_comic(comic_data)
                print(f"[{now()}]    Progress: {chapter_count}/{total_chapters} chapter")
            
            time.sleep(DELAY_CHAPTER)

        # Final save
        save_comic(comic_data)
        existing_comics[url] = comic_data
        print(f"[{now()}]    Selesai: {chapter_count} chapter tersimpan")

    # === SELESAI ===
    print(f"\n[{now()}] SEMUA KOMIK SELESAI DIPROSES!")
    print(f"[{now()}] Total komik: {len(all_comics)}")
    
    # Statistik akhir
    total_chapters = sum(len(comic.get('chapters', [])) for comic in existing_comics.values())
    print(f"[{now()}] Total chapter: {total_chapters}")
    
    save_and_exit()