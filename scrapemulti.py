import requests, json, os, time, signal, sys, re
import concurrent.futures
from bs4 import BeautifulSoup
from datetime import datetime
import threading

# === KONFIGURASI ===
BASE_DIR = "comics"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://komikindo.ch/"
}
DELAY_PAGE = 0.5
DELAY_CHAPTER = 0.3
MAX_THREADS = 5  # Jangan terlalu banyak untuk hindari block
os.makedirs(BASE_DIR, exist_ok=True)

# Thread-safe print
print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# === SAVE ON STOP ===
def save_and_exit(sig=None, frame=None):
    safe_print(f"\n[{now()}] Dihentikan oleh user (Ctrl+C)")
    safe_print(f"[{now()}] SELESAI (aman)! Semua data tersimpan per file.")
    sys.exit(0)

signal.signal(signal.SIGINT, save_and_exit)

# === SANITIZE FILENAME ===
def sanitize_filename(name):
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    name = name.replace(' ', '-')
    return name[:100]

def clean_title(title):
    title = re.sub(r'^Komik\s+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

# === SESSION MANAGEMENT ===
def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

# === GET & SOUP dengan Session ===
def get(session, url):
    try:
        r = session.get(url, timeout=15)
        r.encoding = 'utf-8'
        r.raise_for_status()
        return r.text
    except Exception as e:
        safe_print(f"   Gagal: {e}")
        return None

def soup(session, url):
    html = get(session, url)
    return BeautifulSoup(html, 'html.parser') if html else None

# === SIMPAN KOMIK ===
def save_comic(comic_data):
    title = comic_data['title']
    safe_title = sanitize_filename(title)
    filename = f"{BASE_DIR}/{safe_title}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(comic_data, f, ensure_ascii=False, indent=2)
    safe_print(f"[{now()}]    Simpan: {filename} ({len(comic_data['chapters'])} chapter)")

# === LOAD EXISTING COMICS ===
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
                safe_print(f"   Warning: Gagal baca {filepath}: {e}")
    return existing

# === EXTRACT COMIC INFO ===
def extract_comic_info(session, s_detail, url, list_title):
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
    
    # Cover image
    thumb = s_detail.find('div', class_='thumb')
    if thumb and thumb.find('img'):
        info['cover_image'] = thumb.find('img')['src']
    
    # Info dari .infox
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
    
    # Genre
    genre_elements = s_detail.select('.genre-info a, .series-genres a, .genres a')
    if genre_elements:
        info['genres'] = [a.get_text(strip=True) for a in genre_elements if a.get_text(strip=True)]
    
    # Rating
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
    
    # Votes
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
    
    # Sinopsis
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
    
    # Last updated
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
def extract_chapter_images(session, chapter_url):
    s_ch = soup(session, chapter_url)
    if not s_ch:
        return []
    
    images = []
    containers = [
        s_ch.find('div', id='Baca_Komik'),
        s_ch.find('div', class_='chapter-image'),
        s_ch.select_one('.reader-area'),
        s_ch.select_one('.chapter-body')
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
        safe_print(f"      Warning: Gagal extract title dari parent: {e}")
    
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

# === SCRAPE ALL PAGES ===
def scrape_all_pages(session):
    safe_print(f"[{now()}] Mengambil daftar komik dari SEMUA halaman...")
    all_comics = []
    page = 1
    max_pages = 200  # Safety limit yang tinggi

    while page <= max_pages:
        url = f"https://komikindo.ch/komik-terbaru/page/{page}/" if page > 1 else "https://komikindo.ch/komik-terbaru/"
        safe_print(f"[{now()}] Halaman {page}: {url}")
        
        s = soup(session, url)
        if not s:
            safe_print(f"[{now()}] Gagal akses halaman {page}. Coba lagi...")
            time.sleep(DELAY_PAGE * 2)
            continue

        posts = (s.select('.listupd .animepost .animposx a[itemprop="url"]') or 
                 s.select('.animepost a[itemprop="url"]') or
                 s.select('.animepost .thumb a') or
                 s.select('.film-list a[itemprop="url"]'))

        if not posts:
            safe_print(f"[{now()}] Tidak ada komik di halaman {page}. Selesai.")
            break

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
                safe_print(f"[{now()}]      Found: {title}")

        # Next page detection
        next_btn = s.select_one('a.next.page-numbers')
        if not next_btn:
            safe_print(f"[{now()}] Tidak ditemukan tombol next. Selesai di halaman {page}")
            break
            
        page += 1
        time.sleep(DELAY_PAGE)

    safe_print(f"[{now()}] Ditemukan {len(all_comics)} komik dari {page} halaman.")
    return all_comics

# === PROCESS SINGLE COMIC ===
def process_comic(comic, existing_comics, session, thread_id):
    title, url = comic['title'], comic['url']
    safe_print(f"\n[{now()}] [Thread-{thread_id}] → {title}")
    
    if not url or not url.startswith('http'):
        safe_print(f"[{now()}]    URL tidak valid: {url}")
        return

    # Cek existing
    existing_data = existing_comics.get(url)
    
    if existing_data:
        safe_print(f"[{now()}]    Sudah ada {len(existing_data.get('chapters', []))} chapter. Cek update...")
        
        if existing_data.get('title') != title:
            safe_print(f"[{now()}]    Update title: '{existing_data['title']}' → '{title}'")
            existing_data['title'] = title
        
        existing_chapters = {ch['number'] for ch in existing_data.get('chapters', [])}
        new_chapters = []

        s_detail = soup(session, url)
        if not s_detail:
            safe_print(f"[{now()}]    Gagal akses detail. Skip update.")
            return

        last_update = s_detail.find('span', class_='datech')
        if last_update:
            existing_data['last_updated'] = last_update.get_text(strip=True)

        chapters_data = extract_chapters(s_detail)
        for chapter in chapters_data:
            if chapter['number'] not in existing_chapters:
                safe_print(f"[{now()}]    → Chapter BARU: {chapter['number']}")
                
                images = extract_chapter_images(session, chapter['url'])
                safe_print(f"[{now()}]       Found {len(images)} images")
                
                new_chapters.append({
                    "number": chapter['number'],
                    "url": chapter['url'],
                    "date": chapter['date'],
                    "images": images
                })
                
                time.sleep(DELAY_CHAPTER)

        if new_chapters:
            existing_data['chapters'].extend(new_chapters)
            existing_data['chapters'].sort(key=lambda x: 
                float(re.search(r'[\d.]+', x['number']).group()) if re.search(r'[\d.]+', x['number']) else 0)
            save_comic(existing_data)
            safe_print(f"[{now()}]    Update selesai: +{len(new_chapters)} chapter baru.")
        return

    # KOMIK BARU
    safe_print(f"[{now()}]    Komik baru, mulai scraping...")
    
    s_detail = soup(session, url)
    if not s_detail:
        safe_print(f"[{now()}]    Gagal akses detail. Skip.")
        return

    comic_data = extract_comic_info(session, s_detail, url, title)
    comic_data['chapters'] = []

    chapters_data = extract_chapters(s_detail)
    safe_print(f"[{now()}]    Ditemukan {len(chapters_data)} chapter")

    chapter_count = 0
    total_chapters = len(chapters_data)
    
    for chapter in reversed(chapters_data):
        ch_num, ch_url = chapter['number'], chapter['url']
        safe_print(f"[{now()}]    → Chapter {ch_num} ({chapter_count + 1}/{total_chapters})")

        images = extract_chapter_images(session, ch_url)
        safe_print(f"[{now()}]       Found {len(images)} images")
        
        comic_data['chapters'].append({
            "number": ch_num,
            "url": ch_url,
            "date": chapter['date'],
            "images": images
        })
        
        chapter_count += 1
        
        if chapter_count % 10 == 0 or chapter_count == total_chapters:
            save_comic(comic_data)
            safe_print(f"[{now()}]    Progress: {chapter_count}/{total_chapters} chapter")
        
        time.sleep(DELAY_CHAPTER)

    save_comic(comic_data)
    safe_print(f"[{now()}]    Selesai: {chapter_count} chapter tersimpan")

# === MAIN SCRIPT ===
if __name__ == "__main__":
    safe_print(f"[{now()}] Memulai scraping komik dari KomikIndo...")
    safe_print(f"[{now()}] MODE: MULTITHREADING ({MAX_THREADS} threads)")
    
    # Load existing comics
    existing_comics = get_all_existing_comics()
    safe_print(f"[{now()}] Loaded {len(existing_comics)} existing comics")
    
    # Scrape semua halaman
    with create_session() as session:
        all_comics = scrape_all_pages(session)
    
    safe_print(f"[{now()}] Memulai proses {len(all_comics)} komik dengan {MAX_THREADS} threads...")
    
    # Process comics dengan multithreading
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []
        for i, comic in enumerate(all_comics):
            # Buat session baru untuk setiap thread
            thread_session = create_session()
            future = executor.submit(process_comic, comic, existing_comics, thread_session, i % MAX_THREADS + 1)
            futures.append(future)
            
            # Delay kecil antara submission untuk hindari flood
            time.sleep(0.1)
        
        # Tunggu semua thread selesai
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                safe_print(f"[{now()}] ERROR dalam thread: {e}")

    # === SELESAI ===
    safe_print(f"\n[{now()}] SEMUA KOMIK SELESAI DIPROSES!")
    safe_print(f"[{now()}] Total komik: {len(all_comics)}")
    
    total_chapters = sum(len(comic.get('chapters', [])) for comic in existing_comics.values())
    safe_print(f"[{now()}] Total chapter: {total_chapters}")
    
    save_and_exit()