# scrape_manga.py
import os
import time
import random
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# === KONFIGURASI ===
BASE_URL = "https://komikcast03.com"
LIST_URL = BASE_URL + "/daftar-komik/"
DOWNLOAD_DIR = "manga"
MAX_WORKERS = 3
MAX_PAGES = 9999
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': BASE_URL
}

print_lock = Lock()
metadata_lock = Lock()
all_metadata = []
metadata_file = "manga_metadata.json"

def init():
    global all_metadata
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                all_metadata = json.load(f)
            print(f"[LOADED] {len(all_metadata)} manga dari metadata")
        except:
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
    except:
        pass
    return False

def get_manga_list(page):
    url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
    except:
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    manga_list = []
    for item in soup.select('.list-update_item'):
        a = item.find('a')
        if not a or not a.get('href'): continue
        title = a.find('h3', class_='title').get_text(strip=True) if a.find('h3', class_='title') else "Unknown"
        detail_url = a['href']
        # === FIX: ternary sederhana ===
        latest_chapter = a.find('div', class_='chapter').get_text(strip=True) if a.find('div', class_='chapter') else "Ch.0"
        rating = a.find('div', class_='numscore').get_text(strip=True) if a.find('div', class_='numscore') else "0"
        manga_type = a.find('span', class_='type').get_text(strip=True) if a.find('span', class_='type') else "Unknown"
        manga_list.append({
            'title': title,
            'detail_url': detail_url,
            'latest_chapter': latest_chapter,
            'rating': rating,
            'type': "Manga" if "manga" in manga_type.lower() else "Manhwa"
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
            with print_lock:
                print(f"{thread_id} [SKIP] {manga['title']}")
            return existing

    with requests.Session() as session:
        session.headers.update(HEADERS)
        with print_lock:
            print(f"{thread_id} [START] {manga['title']}")

        try:
            r = session.get(manga['detail_url'], timeout=20)
            if r.status_code != 200:
                with print_lock: print(f"{thread_id} [GAGAL] Status {r.status_code}")
                return None
        except Exception as e:
            with print_lock: print(f"{thread_id} [ERROR] {e}")
            return None

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
        with print_lock:
            print(f"{thread_id} [FOLDER] {manga_folder}")

        cover_img = soup.find('div', class_='komik_info-cover-image')
        cover_url = cover_img.find('img')['src'] if cover_img and cover_img.find('img') else None
        if cover_url and not os.path.exists(os.path.join(manga_folder, "cover.jpg")):
            if download_image(session, cover_url, manga_folder, "cover.jpg"):
                with print_lock: print(f"{thread_id} [OK] Cover")

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

        rating_tag = soup.find('div', class_='data-rating')
        rating = rating_tag['data-ratingkomik'] if rating_tag and rating_tag.get('data-ratingkomik') else "0"

        sinopsis_elem = soup.find('div', class_='komik_info-description-sinopsis')
        sinopsis = sinopsis_elem.get_text(strip=True, separator='\n') if sinopsis_elem else "Tidak ada sinopsis."

        chapters = []
        chapter_list = soup.find('ul', id='chapter-wrapper')
        if chapter_list:
            for item in chapter_list.find_all('li', class_='komik_info-chapters-item'):
                a = item.find('a', class_='chapter-link-item')
                if a and a.get('href'):
                    ch_text = a.get_text(strip=True).replace("Chapter ", "Ch.")
                    chapters.append({'chapter': ch_text, 'url': a['href']})

        existing_chapters = {d.split("_")[-1] for d in os.listdir(manga_folder) if d.startswith("Chapter_")}
        downloaded = 0
        for ch in chapters:
            chap_num = ch['chapter'].split()[-1].zfill(3)
            if chap_num in existing_chapters:
                continue
            try:
                r_ch = session.get(ch['url'], timeout=20)
                if r_ch.status_code != 200: continue
                soup_ch = BeautifulSoup(r_ch.text, 'html.parser')
                body = soup_ch.find('div', id='chapter_body')
                if not body: continue
                imgs = body.find_all('img')
                chap_folder = os.path.join(manga_folder, f"Chapter_{chap_num}")
                os.makedirs(chap_folder, exist_ok=True)
                for idx, img in enumerate(imgs, 1):
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and img_url.startswith('http'):
                        download_image(session, img_url, chap_folder, f"{idx:03d}.jpg")
                    time.sleep(0.2)
                downloaded += 1
                with print_lock: print(f"{thread_id} [OK] {ch['chapter']} → {len(imgs)} gambar")
            except:
                pass
            time.sleep(1.5 + random.uniform(0, 1))

        info = {
            "title": full_title,
            "native": native_title,
            "genre": ", ".join(genres),
            "Released": meta.get('released', 'Unknown'),
            "Author": meta.get('author', 'Unknown'),
            "Status": meta.get('status', 'Unknown'),
            "Type": meta.get('type', manga['type']),
            "Total Chapter": meta.get('total_chapter', '?'),
            "Updated on": meta.get('updated', 'Unknown'),
            "Rating": rating,
            "sinopsis": sinopsis
        }
        with open(os.path.join(manga_folder, "info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

        entry = {
            **info,
            "folder": safe_title,
            "downloaded_chapters": len([d for d in os.listdir(manga_folder) if d.startswith("Chapter_")]),
            "total_available": len(chapters)
        }
        with metadata_lock:
            all_metadata = [m for m in all_metadata if m["folder"] != safe_title] + [entry]

        with print_lock:
            print(f"{thread_id} [SELESAI] {downloaded} chapter baru")
        return entry

def main():
    print("=== MANGA SCRAPER - FULL MODE ===")
    init()

    page = 1
    while True:
        manga_list = get_manga_list(page)
        if not manga_list:
            print(f"[INFO] Halaman {page} kosong. Selesai.")
            break

        with print_lock:
            print(f"\n[HALAMAN {page}] {len(manga_list)} manga ditemukan")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(download_manga, m) for m in manga_list]
            for f in as_completed(futures):
                f.result()

        page += 1
        time.sleep(5)

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(all_metadata, f, ensure_ascii=False, indent=2)

    print(f"\nSELESAI! {len(all_metadata)} manga di: {DOWNLOAD_DIR}")

if __name__ == '__main__':
    main()