import requests, json, os, re
from bs4 import BeautifulSoup
from datetime import datetime
import time

# === KONFIGURASI ===
POPULAR_COMICS_FILE = "popular-comics.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://komikindo.ch/"
}
DELAY = 1.0  # Delay antara request

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def now_iso():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

# === FUNGSI UTAMA ===
def get_soup(url):
    """Dapatkan BeautifulSoup object dari URL"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"[{now()}] Error akses {url}: {e}")
        return None

def clean_title(title):
    """Bersihkan title dari kata 'Komik' dan whitespace berlebihan"""
    title = re.sub(r'^Komik\s+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def extract_popular_comics(soup_obj):
    """Extract data komik terpopuler dari halaman utama"""
    popular_comics = []
    
    # Cari widget komik terpopuler
    popular_widget = soup_obj.find('aside', class_='widgets')
    if not popular_widget:
        print(f"[{now()}] Widget komik terpopuler tidak ditemukan")
        return popular_comics
    
    # Cari section komik terpopuler
    popular_section = popular_widget.find('div', class_='sencs')
    if not popular_section:
        print(f"[{now()}] Section komik terpopuler tidak ditemukan")
        return popular_comics
    
    # Cek judul widget
    widget_title = popular_section.find('h3', class_='widget-title')
    if widget_title and 'Terpopuler' in widget_title.get_text():
        print(f"[{now()}] Found: {widget_title.get_text(strip=True)}")
    
    # Extract setiap komik dari list
    series_list = popular_section.find('div', class_='serieslist pop')
    if not series_list:
        print(f"[{now()}] List komik tidak ditemukan")
        return popular_comics
    
    comics = series_list.find_all('li')
    print(f"[{now()}] Ditemukan {len(comics)} komik terpopuler")
    
    for comic in comics:
        try:
            # Extract ranking
            rank_elem = comic.find('div', class_='ctr')
            rank = rank_elem.get_text(strip=True) if rank_elem else "0"
            
            # Extract title dan URL
            title_elem = comic.find('h4').find('a') if comic.find('h4') else None
            if not title_elem:
                continue
                
            title = clean_title(title_elem.get('title', ''))
            url = title_elem.get('href', '')
            
            # Extract cover image
            img_elem = comic.find('img')
            cover_image = img_elem.get('src', '') if img_elem else ''
            
            # Extract author
            author_elem = comic.find('span', class_='author')
            author = author_elem.get_text(strip=True) if author_elem else ''
            
            # Extract rating/love views
            love_elem = comic.find('span', class_='loveviews')
            rating_text = love_elem.get_text(strip=True) if love_elem else '0'
            # Extract angka dari rating text (contoh: "7", "7.23", "9.33")
            rating_match = re.search(r'(\d+\.\d+|\d+)', rating_text)
            rating = float(rating_match.group(1)) if rating_match else 0.0
            
            # Tentukan kelas ranking (first, second, third, atau biasa)
            rank_class = ""
            if rank_elem:
                if 'first' in rank_elem.get('class', []):
                    rank_class = "first"
                elif 'second' in rank_elem.get('class', []):
                    rank_class = "second"
                elif 'third' in rank_elem.get('class', []):
                    rank_class = "third"
            
            comic_data = {
                "rank": rank,
                "rank_class": rank_class,
                "title": title,
                "url": url,
                "cover_image": cover_image,
                "author": author,
                "rating": rating,
                "scraped_at": now_iso()
            }
            
            popular_comics.append(comic_data)
            print(f"[{now()}]    #{rank}: {title} (Rating: {rating})")
            
        except Exception as e:
            print(f"[{now()}] Error extract komik: {e}")
            continue
    
    return popular_comics

def get_comic_details(comic_url):
    """Dapatkan detail lengkap komik dari halaman detail"""
    print(f"[{now()}]   Mengambil detail dari: {comic_url}")
    
    soup_obj = get_soup(comic_url)
    if not soup_obj:
        return {}
    
    details = {
        "status": "",
        "type": "",
        "genres": [],
        "themes": [],
        "synopsis": "",
        "last_updated": "",
        "total_chapters": 0
    }
    
    try:
        # Extract status, type, dll dari .infox
        infox = soup_obj.find('div', class_='infox')
        if infox:
            for span in infox.find_all('span'):
                text = span.get_text(strip=True)
                
                if "Status:" in text:
                    details['status'] = text.replace("Status:", "").strip()
                
                elif "Jenis Komik:" in text:
                    a = span.find('a')
                    if a:
                        details['type'] = a.get_text(strip=True)
        
        # Extract genres
        genre_elements = soup_obj.select('.genre-info a, .series-genres a, .genres a')
        if genre_elements:
            details['genres'] = [a.get_text(strip=True) for a in genre_elements if a.get_text(strip=True)]
        
        # Extract themes
        theme_elements = soup_obj.select('.infox span:contains("Tema:") a')
        if theme_elements:
            details['themes'] = [a.get_text(strip=True) for a in theme_elements]
        
        # Extract synopsis
        synopsis_selectors = [
            '.entry-content.entry-content-single',
            '.entry-content-single',
            '.synopsis',
            '.description'
        ]
        
        for selector in synopsis_selectors:
            synopsis_elem = soup_obj.select_one(selector)
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
                    details['synopsis'] = '\n'.join(cleaned_lines)
                    break
        
        # Extract last updated
        last_update = soup_obj.find('span', class_='datech')
        if last_update:
            details['last_updated'] = last_update.get_text(strip=True)
        
        # Count total chapters
        chapter_list = soup_obj.find('div', id='chapter_list')
        if chapter_list:
            chapters = chapter_list.find_all('li')
            details['total_chapters'] = len(chapters)
        
    except Exception as e:
        print(f"[{now()}]   Error extract detail: {e}")
    
    return details

def save_popular_comics(comics_data):
    """Simpan data komik terpopuler ke file JSON"""
    try:
        with open(POPULAR_COMICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(comics_data, f, ensure_ascii=False, indent=2)
        print(f"[{now()}] Data disimpan ke: {POPULAR_COMICS_FILE}")
        return True
    except Exception as e:
        print(f"[{now()}] Error menyimpan data: {e}")
        return False

def load_existing_popular_comics():
    """Load data komik terpopuler yang sudah ada"""
    try:
        if os.path.exists(POPULAR_COMICS_FILE):
            with open(POPULAR_COMICS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[{now()}] Error load existing data: {e}")
    return []

def display_stats(comics_data):
    """Tampilkan statistik komik terpopuler"""
    print(f"\n[{now()}] 📊 STATISTIK KOMIK TERPOPULER:")
    print(f"   Total Komik: {len(comics_data)}")
    
    if comics_data:
        top_rated = max(comics_data, key=lambda x: x.get('rating', 0))
        avg_rating = sum(comic.get('rating', 0) for comic in comics_data) / len(comics_data)
        
        print(f"   Rating Tertinggi: {top_rated['rating']} - {top_rated['title']}")
        print(f"   Rating Rata-rata: {avg_rating:.2f}")
        
        # Hitung berdasarkan type
        types = {}
        for comic in comics_data:
            comic_type = comic.get('details', {}).get('type', 'Unknown')
            types[comic_type] = types.get(comic_type, 0) + 1
        
        print(f"   Jenis Komik: {', '.join([f'{k} ({v})' for k, v in types.items()])}")

# === MAIN SCRIPT ===
def main():
    print(f"[{now()}] 🚀 Memulai scraping Komik Terpopuler dari KomikIndo...")
    print(f"[{now()}] URL: https://komikindo.ch/")
    print(f"[{now()}] Output: {POPULAR_COMICS_FILE}")
    
    # Load data yang sudah ada
    existing_data = load_existing_popular_comics()
    print(f"[{now()}] Loaded {len(existing_data)} existing comics")
    
    # Scraping halaman utama
    print(f"\n[{now()}] Mengakses halaman utama...")
    soup_obj = get_soup("https://komikindo.ch/")
    
    if not soup_obj:
        print(f"[{now()}] Gagal mengakses halaman utama")
        return
    
    # Extract komik terpopuler
    popular_comics = extract_popular_comics(soup_obj)
    
    if not popular_comics:
        print(f"[{now()}] Tidak ada komik terpopuler yang ditemukan")
        return
    
    print(f"\n[{now()}] Mengambil detail untuk setiap komik...")
    
    # Ambil detail untuk setiap komik
    for i, comic in enumerate(popular_comics, 1):
        print(f"[{now()}] [{i}/{len(popular_comics)}] {comic['title']}")
        
        # Tambahkan delay untuk menghindari request berlebihan
        time.sleep(DELAY)
        
        # Ambil detail komik
        details = get_comic_details(comic['url'])
        comic['details'] = details
        
        # Tampilkan info singkat
        if details:
            print(f"[{now()}]   → Status: {details.get('status', 'N/A')}")
            print(f"[{now()}]   → Chapters: {details.get('total_chapters', 0)}")
            print(f"[{now()}]   → Genres: {', '.join(details.get('genres', []))}")
    
    # Simpan data
    print(f"\n[{now()}] Menyimpan data...")
    if save_popular_comics(popular_comics):
        display_stats(popular_comics)
        print(f"\n[{now()}] ✅ SELESAI! Data komik terpopuler berhasil disimpan.")
    else:
        print(f"\n[{now()}] ❌ Gagal menyimpan data.")

if __name__ == "__main__":
    main()