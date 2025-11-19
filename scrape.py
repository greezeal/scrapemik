import requests, json, os, time, signal, sys, re
from bs4 import BeautifulSoup
from datetime import datetime

# === KONFIGURASI ===
BASE_DIR = "comics"
SUMMARY_FILE = "comics-summary.json"  # File summary
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://komikindo.ch/"
}
DELAY_PAGE = 1.0
DELAY_CHAPTER = 0.5
os.makedirs(BASE_DIR, exist_ok=True)

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def now_iso():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

# === FUNGSI BARU: BUILD SUMMARY FROM EXISTING COMICS ===
def build_summary_from_existing():
    """Buat summary dari semua komik yang sudah ada di folder comics/"""
    print(f"[{now()}] Membuat summary dari komik yang sudah ada...")
    
    if not os.path.exists(BASE_DIR):
        print(f"[{now()}] Folder {BASE_DIR} tidak ditemukan.")
        return []
    
    comic_files = [f for f in os.listdir(BASE_DIR) if f.endswith('.json')]
    summary = []
    
    for comic_file in comic_files:
        filepath = os.path.join(BASE_DIR, comic_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                comic_data = json.load(f)
            
            # Siapkan data untuk summary
            latest_chapter = {"number": "0", "date": ""}
            chapters = comic_data.get('chapters', [])
            if chapters:
                # Ambil chapter terbaru (diasumsikan sudah sorted)
                latest = chapters[-1]
                latest_chapter = {
                    "number": latest.get('number', '0'),
                    "date": latest.get('date', '')
                }
            
            summary_data = {
                "slug": sanitize_filename(comic_data.get('title', '')),
                "title": comic_data.get('title', ''),
                "cover_image": comic_data.get('cover_image', ''),
                "type": comic_data.get('type', ''),
                "status": comic_data.get('status', ''),
                "genres": comic_data.get('genres', []),
                "themes": comic_data.get('themes', []),
                "rating": comic_data.get('rating', 0.0),
                "last_updated": comic_data.get('last_updated', ''),
                "scraped_at": now_iso(),
                "latestChapter": latest_chapter,
                "url": comic_data.get('url', ''),
                "total_chapters": len(chapters)
            }
            
            summary.append(summary_data)
            print(f"[{now()}]    Ditambahkan ke summary: {comic_data.get('title')}")
            
        except Exception as e:
            print(f"[{now()}]    Error memproses {comic_file}: {e}")
    
    # Simpan summary
    if summary:
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"[{now()}] Summary berhasil dibuat: {len(summary)} komik")
    else:
        print(f"[{now()}] Tidak ada komik yang bisa ditambahkan ke summary")
    
    return summary

# === FUNGSI BARU: VALIDATE AND FIX SUMMARY ===
def validate_and_fix_summary():
    """Validasi dan perbaiki summary jika ada ketidaksesuaian dengan komik yang ada"""
    print(f"[{now()}] Memvalidasi summary...")
    
    if not os.path.exists(SUMMARY_FILE):
        print(f"[{now()}] Summary file tidak ditemukan, membuat baru...")
        return build_summary_from_existing()
    
    try:
        # Load summary yang ada
        with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
            existing_summary = json.load(f)
        
        # Load semua komik yang ada
        existing_comics = get_all_existing_comics()
        
        # Buat mapping untuk pengecekan
        summary_urls = {item.get('url') for item in existing_summary if item.get('url')}
        comic_urls = set(existing_comics.keys())
        
        # Cari komik yang ada di folder tapi tidak di summary
        missing_in_summary = comic_urls - summary_urls
        missing_in_folder = summary_urls - comic_urls
        
        if missing_in_summary:
            print(f"[{now()}] Ditemukan {len(missing_in_summary)} komik yang belum ada di summary")
            
            for url in missing_in_summary:
                comic_data = existing_comics[url]
                update_comics_summary(comic_data)
                print(f"[{now()}]    Ditambahkan: {comic_data.get('title')}")
        
        if missing_in_folder:
            print(f"[{now()}] Ditemukan {len(missing_in_folder)} komik di summary yang tidak ada di folder")
            
            # Hapus dari summary
            new_summary = [item for item in existing_summary if item.get('url') not in missing_in_folder]
            
            with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_summary, f, ensure_ascii=False, indent=2)
            
            print(f"[{now()}]    Dihapus dari summary: {len(missing_in_folder)} komik")
        
        if not missing_in_summary and not missing_in_folder:
            print(f"[{now()}] Summary sudah sinkron dengan komik yang ada")
            
        return True
        
    except Exception as e:
        print(f"[{now()}] Error validasi summary: {e}")
        # Jika error, buat summary baru
        return build_summary_from_existing()

# === FUNGSI BARU: UPDATE COMICS SUMMARY ===
def update_comics_summary(comic_data):
    """Update atau tambah data komik ke comics-summary.json"""
    try:
        # Load existing summary jika ada
        if os.path.exists(SUMMARY_FILE):
            with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
                summary = json.load(f)
        else:
            summary = []
        
        # Cari komik yang sudah ada berdasarkan slug/URL
        comic_slug = comic_data.get('slug') or sanitize_filename(comic_data.get('title', ''))
        existing_index = -1
        
        for i, item in enumerate(summary):
            if (item.get('slug') == comic_slug or 
                item.get('url') == comic_data.get('url') or
                item.get('title') == comic_data.get('title')):
                existing_index = i
                break
        
        # Siapkan data untuk summary
        latest_chapter = {"number": "0", "date": ""}
        chapters = comic_data.get('chapters', [])
        if chapters:
            # Ambil chapter terbaru (diasumsikan sudah sorted)
            latest = chapters[-1]
            latest_chapter = {
                "number": latest.get('number', '0'),
                "date": latest.get('date', '')
            }
        
        summary_data = {
            "slug": comic_slug,
            "title": comic_data.get('title', ''),
            "cover_image": comic_data.get('cover_image', ''),
            "type": comic_data.get('type', ''),
            "status": comic_data.get('status', ''),
            "genres": comic_data.get('genres', []),
            "themes": comic_data.get('themes', []),
            "rating": comic_data.get('rating', 0.0),
            "last_updated": comic_data.get('last_updated', ''),
            "scraped_at": now_iso(),
            "latestChapter": latest_chapter,
            "url": comic_data.get('url', ''),
            "total_chapters": len(chapters)
        }
        
        # Update atau tambah data
        if existing_index >= 0:
            summary[existing_index] = summary_data
            print(f"[{now()}]    Update summary: {comic_data.get('title')}")
        else:
            summary.append(summary_data)
            print(f"[{now()}]    Tambah ke summary: {comic_data.get('title')}")
        
        # Simpan file summary
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
        return True
        
    except Exception as e:
        print(f"[{now()}]    Error update summary: {e}")
        return False

# === FUNGSI BARU: REMOVE FROM SUMMARY ===
def remove_from_summary(comic_url):
    """Hapus komik dari summary berdasarkan URL"""
    try:
        if not os.path.exists(SUMMARY_FILE):
            return
            
        with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        # Filter out comic dengan URL yang sesuai
        new_summary = [item for item in summary if item.get('url') != comic_url]
        
        if len(new_summary) < len(summary):
            with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_summary, f, ensure_ascii=False, indent=2)
            print(f"[{now()}]    Hapus dari summary: {comic_url}")
            
    except Exception as e:
        print(f"[{now()}]    Error remove from summary: {e}")

# === FUNGSI BARU: GET SUMMARY STATS ===
def get_summary_stats():
    """Dapatkan statistik dari summary file"""
    try:
        if not os.path.exists(SUMMARY_FILE):
            return {"total_comics": 0, "ongoing": 0, "completed": 0}
        
        with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        ongoing = len([item for item in summary if item.get('status') == 'Ongoing'])
        completed = len([item for item in summary if item.get('status') == 'Completed'])
        
        return {
            "total_comics": len(summary),
            "ongoing": ongoing,
            "completed": completed
        }
    except Exception as e:
        print(f"[{now()}]    Error get summary stats: {e}")
        return {"total_comics": 0, "ongoing": 0, "completed": 0}

# === SAVE ON STOP ===
def save_and_exit(sig=None, frame=None):
    print(f"\n[{now()}] Dihentikan oleh user (Ctrl+C)")
    
    # Tampilkan statistik summary
    stats = get_summary_stats()
    print(f"[{now()}] Statistik Summary: {stats['total_comics']} komik ({stats['ongoing']} ongoing, {stats['completed']} completed)")
    
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

# === SAFE CHAPTER SORTING ===
def safe_chapter_sort(chapters):
    """Safe chapter sorting dengan handling error untuk format bermasalah"""
    def get_chapter_num(ch):
        num_str = ch['number']
        try:
            # Clean the string - hapus karakter non-numeric kecuali titik
            cleaned = re.sub(r'[^\d.]', '', num_str)
            # Fix double dots dan multiple dots
            while '..' in cleaned:
                cleaned = cleaned.replace('..', '.')
            # Hapus titik di awal atau akhir
            cleaned = cleaned.strip('.')
            # Pastikan tidak empty dan valid
            if cleaned and cleaned != '.':
                return float(cleaned)
            return 0
        except (ValueError, AttributeError):
            return 0
    
    # Sort dengan key yang aman
    chapters.sort(key=get_chapter_num)
    return chapters

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
    
    # UPDATE SUMMARY SETELAH SIMPAN KOMIK
    update_comics_summary(comic_data)

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
    print(f"[{now()}] Summary file: {SUMMARY_FILE}")
    
    # === VALIDASI SUMMARY SEBELUM MEMULAI ===
    validate_and_fix_summary()
    
    # Load existing comics
    existing_comics = get_all_existing_comics()
    print(f"[{now()}] Loaded {len(existing_comics)} existing comics")
    
    # Tampilkan statistik summary awal
    initial_stats = get_summary_stats()
    print(f"[{now()}] Summary awal: {initial_stats['total_comics']} komik terdaftar")

    # === SCRAPING SEMUA HALAMAN ===
    print(f"[{now()}] Mengambil daftar komik dari semua halaman...")
    all_comics = []
    page = 1
    MAX_PAGES = 3  # Safety limit

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
                # PERBAIKAN: Gunakan safe chapter sorting
                existing_data['chapters'] = safe_chapter_sort(existing_data['chapters'])
                save_comic(existing_data)
                print(f"[{now()}]    Update selesai: +{len(new_chapters)} chapter baru.")
            else:
                print(f"[{now()}]    Tidak ada chapter baru.")
                # Update summary meskipun tidak ada chapter baru (untuk update last_updated dll)
                update_comics_summary(existing_data)
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

        # Final save dengan sorting yang aman
        comic_data['chapters'] = safe_chapter_sort(comic_data['chapters'])
        save_comic(comic_data)
        existing_comics[url] = comic_data
        print(f"[{now()}]    Selesai: {chapter_count} chapter tersimpan")

    # === SELESAI ===
    print(f"\n[{now()}] SEMUA KOMIK SELESAI DIPROSES!")
    print(f"[{now()}] Total komik: {len(all_comics)}")
    
    # Statistik akhir
    total_chapters = sum(len(comic.get('chapters', [])) for comic in existing_comics.values())
    print(f"[{now()}] Total chapter: {total_chapters}")
    
    # Tampilkan statistik summary akhir
    final_stats = get_summary_stats()
    print(f"[{now()}] Statistik Summary: {final_stats['total_comics']} komik ({final_stats['ongoing']} ongoing, {final_stats['completed']} completed)")
    
    save_and_exit()