# scrape_manga.py
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
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({"last_page": page}, f, indent=2)

def load_state():
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_page", 0)
        except:
            return 0
    return 0

def init():
    global all_metadata
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                all_metadata = json.load(f)
            log(f"LOADED {len(all_metadata)} manga dari metadata")
        except:
            all_metadata = []

def download_image(session, img_url, folder, filename):
    try:
        r = session.get(img_url, timeout=10)
        if r.status_code == 200:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, filename)
            with open(path, 'wb') as f:
                f.write(r.content)
            return True
    except:
        pass
    return False

def get_manga_list(page):
    url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
    log(f"→ Halaman {page}: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            log(f"GAGAL: status {r.status_code}")
            return []
    except Exception as e:
        log(f"ERROR: {e}")
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    items = soup.select('.list-update_item')
    log(f"Ditemukan {len(items)} manga")
    manga_list = []
    for item in items:
        a = item.find('a')
        if not a or not a.get('href'): continue
        title = a.find('h3', class_='title').get_text(strip=True) if a.find('h3', class_='title') else "Unknown"
        detail_url = a['href']
        latest_chapter = a.find('div', class_='chapter').get_text(strip=True) if a.find('div', class_='chapter') else "Ch.0"
        manga_list.append({
            'title': title,
            'detail_url': detail_url,
            'latest_chapter': latest_chapter
        })
    return manga_list

def download_manga(manga):
    global all_metadata
    thread_id = f"[T{random.randint(100,999)}]"
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in manga['title'])
    safe_title = safe_title.replace(" ", "_")[:100].strip("_")
    manga_folder = os.path.join(DOWNLOAD_DIR, safe_title)

    if os.path.exists(manga_folder):
        existing = next((m for m in all_metadata if m["folder"] == safe_title), None)
        if existing:
            log(f"{thread_id} [SKIP] {manga['title']}")
            return existing

    with requests.Session() as session:
        session.headers.update(HEADERS)
        log(f"{thread_id} [START] {manga['title']}")

        try:
            r = session.get(manga['detail_url'], timeout=15)
            if r.status_code != 200: return None
        except: return None

        soup = BeautifulSoup(r.text, 'html.parser')
        title_elem = soup.find('h1', class_='komik_info-content-body-title')
        full_title = title_elem.get_text(strip=True) if title_elem else manga['title']
        title = full_title.replace(" Bahasa Indonesia", "")
        native_elem = soup.find('span', class_='komik_info-content-native')
        native_title = native_elem.get_text(strip=True) if native_elem else ""

        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        safe_title = safe_title.replace(" ", "_")[:100].strip("_")
        manga_folder = os.path.join(DOWNLOAD_DIR, safe_title)
        os.makedirs(manga_folder, exist_ok=True)

        # Cover
        cover_img = soup.find('div', class_='komik_info-cover-image')
        cover_url = cover_img.find('img')['src'] if cover_img and cover_img.find('img') else None
        if cover_url and not os.path.exists(os.path.join(manga_folder, "cover.jpg")):
            download_image(session, cover_url, manga_folder, "cover.jpg")

        # Metadata
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
        sinopsis = soup.find('div', class_='komik_info-description-sinopsis').get_text(strip=True, separator='\n') if soup.find('div', class_='komik_info-description-sinopsis') else "Tidak ada sinopsis."

        # Chapter (hanya 1 chapter baru)
        chapters = []
        chapter_list = soup.find('ul', id='chapter-wrapper')
        if chapter_list:
            for item in chapter_list.find_all('li', class_='komik_info-chapters-item')[:1]:  # HANYA 1 CHAPTER
                a = item.find('a', class_='chapter-link-item')
                if a and a.get('href'):
                    ch_text = a.get_text(strip=True).replace("Chapter ", "Ch.")
                    chapters.append({'chapter': ch_text, 'url': a['href']})

        downloaded = 0
        for ch in chapters:
            chap_num = ch['chapter'].split()[-1].zfill(3)
            chap_folder = os.path.join(manga_folder, f"Chapter_{chap_num}")
            if os.path.exists(chap_folder): continue
            try:
                r_ch = session.get(ch['url'], timeout=15)
                if r_ch.status_code != 200: continue
                soup_ch = BeautifulSoup(r_ch.text, 'html.parser')
                body = soup_ch.find('div', id='chapter_body')
                if not body: continue
                imgs = body.find_all('img')
                os.makedirs(chap_folder, exist_ok=True)
                for idx, img in enumerate(imgs, 1):
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and img_url.startswith('http'):
                        download_image(session, img_url, chap_folder, f"{idx:03d}.jpg")
                downloaded += 1
                log(f"{thread_id} [OK] {ch['chapter']}")
            except:
                pass

        # Simpan info.json
        info = {
            "title": full_title,
            "native": native_title,
            "genre": ", ".join(genres),
            "Released": meta.get('released', 'Unknown'),
            "Author": meta.get('author', 'Unknown'),
            "Status": meta.get('status', 'Unknown'),
            "Type": meta.get('type', 'Unknown'),
            "Total Chapter": meta.get('total_chapter', '?'),
            "Updated on": meta.get('updated', 'Unknown'),
            "Rating": rating,
            "sinopsis": sinopsis
        }
        with open(os.path.join(manga_folder, "info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

        entry = {**info, "folder": safe_title, "downloaded_chapters": downloaded}
        with metadata_lock:
            all_metadata = [m for m in all_metadata if m["folder"] != safe_title] + [entry]

        log(f"{thread_id} [SELESAI] {downloaded} chapter")
        return entry

def main():
    log("=== SMART MANGA SCRAPER ===")
    init()
    start_page = load_state() + 1
    log(f"Resume dari halaman {start_page}")

    manga_list = get_manga_list(start_page)
    if not manga_list:
        log("Tidak ada data. Mungkin sudah selesai.")
        save_state(start_page - 1)
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_manga, m) for m in manga_list]
        for f in as_completed(futures):
            f.result()

    save_state(start_page)
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(all_metadata, f, ensure_ascii=False, indent=2)

    log(f"SELESAI halaman {start_page} → lanjut besok!")

if __name__ == '__main__':
    main()