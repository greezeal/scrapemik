# scrape_manga_debug.py
import os
import time
import random
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

# === KONFIG ===
BASE_URL = "https://komikcast03.com"
LIST_URL = BASE_URL + "/daftar-komik/"
DOWNLOAD_DIR = "manga"
MAX_WORKERS = 3
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': BASE_URL
}

print_lock = Lock()
metadata_lock = Lock()
all_metadata = []
metadata_file = "manga_metadata.json"
state_file = "state.json"

def log(msg):
    with print_lock:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] {msg}")

def save_state(page):
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"last_page": page}, f, indent=2)
        log(f"State disimpan: halaman {page}")
    except Exception as e:
        log(f"GAGAL simpan state: {e}")

def load_state():
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                page = data.get("last_page", 0)
                log(f"Resume dari halaman {page + 1}")
                return page
        except Exception as e:
            log(f"GAGAL baca state: {e}")
    return 0

def init():
    global all_metadata
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    log(f"Folder: {os.path.abspath(DOWNLOAD_DIR)}")
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                all_metadata = json.load(f)
            log(f"LOADED {len(all_metadata)} manga dari metadata")
        except Exception as e:
            log(f"GAGAL baca metadata: {e}")
            all_metadata = []

def download_image(session, img_url, folder, filename):
    try:
        r = session.get(img_url, timeout=15)
        if r.status_code == 200:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, filename)
            with open(path, 'wb') as f:
                f.write(r.content)
            return True
        else:
            log(f"GAMBAR GAGAL: {img_url} → {r.status_code}")
    except Exception as e:
        log(f"GAMBAR ERROR: {img_url} → {e}")
    return False

def get_manga_list(page):
    url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
    log(f"Mengambil: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        log(f"Status: {r.status_code}")
        if r.status_code != 200:
            log(f"GAGAL halaman {page}: status {r.status_code}")
            return []
    except Exception as e:
        log(f"KONEKSI GAGAL: {e}")
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    items = soup.select('.list-update_item')
    log(f"Ditemukan {len(items)} item di halaman {page}")
    if not items:
        log("Tidak ada .list-update_item → situs mungkin berubah!")
        return []

    manga_list = []
    for item in items:
        a = item.find('a')
        if not a or not a.get('href'):
            log("Item tanpa link!")
            continue
        title_tag = a.find('h3', class_='title')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"
        detail_url = a['href']
        chapter_tag = a.find('div', class_='chapter')
        latest_chapter = chapter_tag.get_text(strip=True) if chapter_tag else "Ch.0"
        manga_list.append({
            'title': title,
            'detail_url': detail_url,
            'latest_chapter': latest_chapter
        })
    log(f"→ {len(manga_list)} manga valid")
    return manga_list

def download_manga(manga):
    global all_metadata
    thread_id = f"[T{random.randint(100,999)}]"
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in manga['title'])
    safe_title = safe_title.replace(" ", "_")[:100].strip("_")
    manga_folder = os.path.join(DOWNLOAD_DIR, safe_title)

    # Cek duplikasi
    if os.path.exists(manga_folder):
        existing = next((m for m in all_metadata if m["folder"] == safe_title), None)
        if existing:
            log(f"{thread_id} [SKIP] {manga['title']}")
            return existing

    log(f"{thread_id} [START] {manga['title']}")
    with requests.Session() as session:
        session.headers.update(HEADERS)

        # === DETAIL PAGE ===
        try:
            r = session.get(manga['detail_url'], timeout=20)
            log(f"{thread_id} Detail → {r.status_code}")
            if r.status_code != 200:
                log(f"{thread_id} GAGAL detail: {r.status_code}")
                return None
        except Exception as e:
            log(f"{thread_id} ERROR detail: {e}")
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        # === JUDUL ===
        title_elem = soup.find('h1', class_='komik_info-content-body-title')
        full_title = title_elem.get_text(strip=True) if title_elem else manga['title']
        title = full_title.replace(" Bahasa Indonesia", "")
        log(f"{thread_id} Judul: {title}")

        # === FOLDER ===
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        safe_title = safe_title.replace(" ", "_")[:100].strip("_")
        manga_folder = os.path.join(DOWNLOAD_DIR, safe_title)
        os.makedirs(manga_folder, exist_ok=True)
        log(f"{thread_id} Folder: {manga_folder}")

        # === COVER ===
        cover_img = soup.find('div', class_='komik_info-cover-image')
        cover_url = None
        if cover_img and cover_img.find('img'):
            cover_url = cover_img.find('img')['src']
            if cover_url and not os.path.exists(os.path.join(manga_folder, "cover.jpg")):
                if download_image(session, cover_url, manga_folder, "cover.jpg"):
                    log(f"{thread_id} [OK] Cover")

        # === METADATA ===
        genres = [a.get_text(strip=True) for a in soup.select('.komik_info-content-genre a')]
        meta = {}
        for span in soup.select('.komik_info-content-meta span'):
            text = span.get_text(strip=True)
            if 'Released:' in text: meta['released'] = text.split(':', 1)[1].strip()
            elif 'Author:' in text: meta['author'] = text.split(':', 1)[1].strip()
            elif 'Status:' in text: meta['status'] = text.split(':', 1)[1].strip()
            elif 'Type:' in text:
                a_tag = span.find('a')
                meta['type'] = a_tag.get_text(strip=True) if a_tag else text.split(':', 1)[1].strip()
            elif 'Total Chapter:' in text: meta['total_chapter'] = text.split(':', 1)[1].strip()
            elif 'Updated on:' in text:
                time_tag = span.find('time')
                meta['updated'] = time_tag.get_text(strip=True) if time_tag else text.split(':', 1)[1].strip()

        rating = soup.find('div', class_='data-rating')['data-ratingkomik'] if soup.find('div', class_='data-rating') else "0"
        sinopsis = soup.find('div', class_='komik_info-description-sinopsis')
        sinopsis_text = sinopsis.get_text(strip=True, separator='\n') if sinopsis else "Tidak ada sinopsis."

        # === SIMPAN info.json (PASTIKAN FOLDER ADA) ===
        info = {
            "title": full_title,
            "native": soup.find('span', class_='komik_info-content-native').get_text(strip=True) if soup.find('span', class_='komik_info-content-native') else "",
            "genre": ", ".join(genres),
            "Released": meta.get('released', 'Unknown'),
            "Author": meta.get('author', 'Unknown'),
            "Status": meta.get('status', 'Unknown'),
            "Type": meta.get('type', 'Unknown'),
            "Total Chapter": meta.get('total_chapter', '?'),
            "Updated on": meta.get('updated', 'Unknown'),
            "Rating": rating,
            "sinopsis": sinopsis_text
        }

        info_path = os.path.join(manga_folder, "info.json")
        try:
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
            log(f"{thread_id} [OK] info.json disimpan")
        except Exception as e:
            log(f"{thread_id} GAGAL simpan info.json: {e}")

        # === CHAPTER (1 chapter baru) ===
        chapter_list = soup.find('ul', id='chapter-wrapper')
        if chapter_list:
            first_ch = chapter_list.find('li', class_='komik_info-chapters-item')
            if first_ch:
                a = first_ch.find('a', class_='chapter-link-item')
                if a and a.get('href'):
                    ch_text = a.get_text(strip=True).replace("Chapter ", "Ch.")
                    ch_url = a['href']
                    chap_num = ch_text.split()[-1].zfill(3)
                    chap_folder = os.path.join(manga_folder, f"Chapter_{chap_num}")
                    if not os.path.exists(chap_folder):
                        os.makedirs(chap_folder, exist_ok=True)
                        try:
                            r_ch = session.get(ch_url, timeout=15)
                            if r_ch.status_code == 200:
                                soup_ch = BeautifulSoup(r_ch.text, 'html.parser')
                                body = soup_ch.find('div', id='chapter_body')
                                if body:
                                    imgs = body.find_all('img')
                                    for idx, img in enumerate(imgs, 1):
                                        img_url = img.get('src') or img.get('data-src')
                                        if img_url and img_url.startswith('http'):
                                            download_image(session, img_url, chap_folder, f"{idx:03d}.jpg")
                                    log(f"{thread_id} [OK] {ch_text} → {len(imgs)} gambar")
                        except Exception as e:
                            log(f"{thread_id} GAGAL chapter: {e}")

        # === UPDATE METADATA ===
        entry = {**info, "folder": safe_title, "downloaded_chapters": 1 if os.path.exists(os.path.join(manga_folder, "Chapter_")) else 0}
        with metadata_lock:
            all_metadata = [m for m in all_metadata if m["folder"] != safe_title] + [entry]

        log(f"{thread_id} [SELESAI] {manga['title']}")
        return entry

def main():
    log("=== DEBUG MODE: MANGA SCRAPER ===")
    init()
    start_page = load_state() + 1

    manga_list = get_manga_list(start_page)
    if not manga_list:
        log("TIDAK ADA DATA → cek koneksi atau struktur HTML berubah")
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_manga, m) for m in manga_list]
        for f in as_completed(futures):
            f.result()

    save_state(start_page)
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(all_metadata, f, ensure_ascii=False, indent=2)
        log(f"Metadata disimpan: {len(all_metadata)} manga")
    except Exception as e:
        log(f"GAGAL simpan metadata: {e}")

    log(f"SELESAI! Cek folder: {os.path.abspath(DOWNLOAD_DIR)}")

if __name__ == '__main__':
    main()