# -*- coding: utf-8 -*-
"""
3-LAYER ANTI-DUPLICATE LEDGER & R630 -> LAPTOP OFFLINE VIDEO CACHE SYNC
Chay truc tiep tren Laptop (C:\\TikTok_AutoHub\\):
1. So cai SQLite (anti_duplicate_ledger.db) khoa cung 3 lop:
   - Lop 1: file_sha256 (ma bam nhi phan cua file video .mp4) -> Khong bao gio dang lai cung 1 file
   - Lop 2: clip_id + channel (ma clip goc LiveVault tren tung kenh) -> Khong bao gio dang trung clip goc tren cung kenh
   - Lop 3: caption_sha256 (ma bam noi dung Caption) -> Khong bao gio dang trung Caption
2. Tu dong dong bo (Pre-Cache) video da cat tu Server R630 (192.168.1.240:8088 hoac IP Tailscale)
   ve o C:\\TikTok_AutoHub\\video_cache\\ tren Laptop de khi mang Laptop + Oppo A57 ra ngoai
   khac mang voi R630 van co san kho video dang suot ca ngay theo nhip 1 tieng / 1 video!
"""
import hashlib
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HUB_DIR = Path(r"C:\TikTok_AutoHub")
DATA_DIR = HUB_DIR / "data"
CACHE_DIR = HUB_DIR / "video_cache"
for d in (HUB_DIR, DATA_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "anti_duplicate_ledger.db"
LOCAL_QUEUE_FILE = DATA_DIR / "local_queue.json"
SETTINGS_FILE = DATA_DIR / "hub_settings.json"

ALLOWED_CHANNELS = ["@suckhoeviet.2", "@suc.khoe.vang.268"]


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS posted_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT UNIQUE,
            clip_id TEXT,
            channel TEXT,
            product_name TEXT,
            file_sha256 TEXT,
            caption_sha256 TEXT,
            posted_at TEXT,
            post_mode TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_file_sha ON posted_history(file_sha256)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_clip_ch ON posted_history(clip_id, channel)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cap_sha ON posted_history(caption_sha256)")
    conn.commit()
    conn.close()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    norm = " ".join(text.strip().lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def check_duplicate_guard(item: dict, local_video_path: Path) -> tuple[bool, str, str, str]:
    """
    Kiem tra 3 lop chong trung lap truoc khi cho phep dang len Oppo A57.
    Tra ve: (is_safe, reason, file_hash, caption_hash)
    """
    init_db()
    ch = item.get("channel", "")
    if ch not in ALLOWED_CHANNELS:
        return False, f"Kênh '{ch}' không nằm trong 2 kênh được phép đăng trên Oppo A57 ({ALLOWED_CHANNELS})", "", ""

    if not local_video_path.exists() or local_video_path.stat().st_size < 50000:
        return False, f"File video chưa tồn tại hoặc bị lỗi dung lượng: {local_video_path}", "", ""

    f_hash = sha256_file(local_video_path)
    c_hash = sha256_text(item.get("caption_seo", ""))
    clip_id = item.get("clip_id") or item.get("id", "").split("_")[1]

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Lop 1: Kiem tra trung file nhi phan SHA-256 tren TOAN HE THONG (ca 4 kenh)
    cur.execute("SELECT channel, posted_at FROM posted_history WHERE file_sha256 = ?", (f_hash,))
    row = cur.fetchone()
    if row:
        conn.close()
        return False, f"CHẶN TRÙNG LỚP 1 (Trùng mã băm video SHA-256): Video này đã đăng trên {row[0]} lúc {row[1]}", f_hash, c_hash

    # Lop 2: Kiem tra trung clip goc LiveVault tren cung 1 kenh
    cur.execute("SELECT posted_at FROM posted_history WHERE clip_id = ? AND channel = ?", (clip_id, ch))
    row = cur.fetchone()
    if row:
        conn.close()
        return False, f"CHẶN TRÙNG LỚP 2 (Trùng clip nguồn '{clip_id}' trên kênh {ch} lúc {row[0]})", f_hash, c_hash

    # Lop 3: Kiem tra trung Caption SEO tren TOAN HE THONG
    cur.execute("SELECT channel, posted_at FROM posted_history WHERE caption_sha256 = ?", (c_hash,))
    row = cur.fetchone()
    if row:
        conn.close()
        return False, f"CHẶN TRÙNG LỚP 3 (Trùng nội dung Caption với bài trên {row[0]} lúc {row[1]})", f_hash, c_hash

    conn.close()
    return True, "HỢP LỆ 100% — Đã vượt qua 3 lớp kiểm tra chống trùng lặp", f_hash, c_hash


def record_posted_in_ledger(item: dict, f_hash: str, c_hash: str, mode: str = "AUTO_OPPO") -> None:
    """Ghi khoa vinh vien vao So cai SQLite + danh dau POSTED trong local_queue.json & R630."""
    init_db()
    clip_id = item.get("clip_id") or item.get("id", "").split("_")[1]
    now_str = datetime.now().strftime("%H:%M:%S · %d/%m/%Y")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO posted_history
        (item_id, clip_id, channel, product_name, file_sha256, caption_sha256, posted_at, post_mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item.get("id"), clip_id, item.get("channel"), item.get("product_name"), f_hash, c_hash, now_str, mode),
    )
    conn.commit()
    conn.close()

    # Cap nhat local queue
    if LOCAL_QUEUE_FILE.exists():
        try:
            q = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
            for x in q:
                if x.get("id") == item.get("id"):
                    x["status"] = "POSTED"
                    x["posted_at"] = now_str
            LOCAL_QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # Bao nguoc ve R630 neu dang cung mang
    r630_url = get_settings().get("r630_url", "http://192.168.1.240:8088").rstrip("/")
    try:
        req = urllib.request.Request(f"{r630_url}/api/mark_posted?id={item.get('id')}", method="POST")
        urllib.request.urlopen(req, timeout=4).read()
    except Exception:
        pass


def get_ledger_history(limit: int = 30) -> list[dict]:
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT item_id, clip_id, channel, product_name, file_sha256, posted_at, post_mode FROM posted_history ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "item_id": r[0],
            "clip_id": r[1],
            "channel": r[2],
            "product_name": r[3],
            "file_sha256": r[4][:16] + "...",
            "posted_at": r[5],
            "post_mode": r[6],
        }
        for r in rows
    ]


def get_settings() -> dict:
    default = {
        "r630_url": "https://tiktok.phamvuong.io.vn",
        "r630_lan_url": "http://192.168.1.240:8088",
        "r630_cloudflare_url": "https://tiktok.phamvuong.io.vn",
        "oppo_last_ip": "192.168.1.95",
        "interval_minutes": 60,
        "auto_scheduler_enabled": True,
        "post_mode": "PREPARE_AND_FILL",
        "active_channels": ["@suckhoeviet.2", "@suc.khoe.vang.268"],
        "max_offline_cache_videos": 60,
    }
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            default.update(saved)
        except Exception:
            pass
    SETTINGS_FILE.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    return default


def resolve_active_r630_url() -> str:
    """Tu dong chon LAN (http://192.168.1.240:8088) khi o nha hoac Cloudflare Tunnel (https://tiktok.phamvuong.io.vn) khi di ra ngoai!"""
    for candidate in ("http://192.168.1.240:8088", "https://tiktok.phamvuong.io.vn"):
        try:
            req = urllib.request.Request(f"{candidate}/api/queue", headers={"User-Agent": "TikTok-AutoHub/2.0"})
            urllib.request.urlopen(req, timeout=3.5).read(64)
            return candidate
        except Exception:
            pass
    return "https://tiktok.phamvuong.io.vn"


def sync_from_r630_to_laptop_cache() -> dict:
    """
    Dong bo danh sach Queue & tai truoc (Pre-cache) cac video tiep theo tu R630
    (qua LAN 192.168.1.240:8088 hoac qua Cloudflare https://tiktok.phamvuong.io.vn khi di ra ngoai!).
    """
    cfg = get_settings()
    r630_url = resolve_active_r630_url()
    cfg["r630_url"] = r630_url
    SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    max_cache = cfg.get("max_offline_cache_videos", 16)

    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT item_id, clip_id, channel FROM posted_history")
    rows = cur.fetchall()
    already_posted_ids = {r[0] for r in rows}
    already_posted_clip_ch = {(r[1], r[2]) for r in rows}
    conn.close()

    r630_reachable = False
    remote_queue = []
    try:
        req = urllib.request.Request(f"{r630_url}/api/queue", headers={"User-Agent": "TikTok-AutoHub/2.0"})
        raw = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")
        remote_queue = json.loads(raw)
        r630_reachable = True
    except Exception:
        r630_reachable = False

    local_queue = []
    if LOCAL_QUEUE_FILE.exists():
        try:
            local_queue = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            local_queue = []

    if r630_reachable and remote_queue:
        by_id = {x["id"]: x for x in local_queue}
        # Giu nguyen cac video vua cat truc tiep tren Laptop o DAU danh sach
        remote_ids = {item["id"] for item in remote_queue}
        local_only = [x for x in local_queue if x["id"] not in remote_ids and x.get("status") != "POSTED"]
        merged = list(local_only)
        for item in remote_queue:
            if item.get("channel") not in ALLOWED_CHANNELS:
                continue
            iid = item["id"]
            cid = item.get("clip_id") or iid.split("_")[1]
            ch = item.get("channel", "")
            # Neu clip_id da bi khoa trong posted_history (bao gom ca OLD_TEST_SKIPPED), BO QUA LUON!
            if iid in already_posted_ids or (cid, ch) in already_posted_clip_ch or (cid, "ALL_CHANNELS") in already_posted_clip_ch:
                continue
            elif iid in by_id and by_id[iid].get("status") in ("POSTED", "SAVED_DRAFT"):
                item["status"] = by_id[iid].get("status")
                if "drafted_at" in by_id[iid]:
                    item["drafted_at"] = by_id[iid]["drafted_at"]
            merged.append(item)
        local_queue = merged

    # Download video files into C:\TikTok_AutoHub\video_cache\ for top N ready items
    downloaded_now = 0
    cached_total = 0
    for item in local_queue:
        if item.get("status") == "POSTED":
            continue
        fname = Path(item.get("output_video", "")).name
        if not fname:
            continue
        local_mp4 = CACHE_DIR / fname
        item["local_cache_path"] = str(local_mp4)
        if local_mp4.exists() and local_mp4.stat().st_size > 50000:
            item["cached_offline"] = True
            cached_total += 1
        elif r630_reachable and cached_total < max_cache:
            try:
                dl_url = f"{r630_url}/download?file={urllib.parse.quote(item['output_video'])}"
                urllib.request.urlretrieve(dl_url, str(local_mp4))
                if local_mp4.exists() and local_mp4.stat().st_size > 50000:
                    item["cached_offline"] = True
                    cached_total += 1
                    downloaded_now += 1
            except Exception:
                item["cached_offline"] = False
        else:
            item["cached_offline"] = False

    LOCAL_QUEUE_FILE.write_text(json.dumps(local_queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "r630_online": r630_reachable,
        "total_queue": len([x for x in local_queue if x.get("status") != "POSTED"]),
        "cached_offline_ready": cached_total,
        "downloaded_now": downloaded_now,
    }


if __name__ == "__main__":
    import urllib.parse
    init_db()
    res = sync_from_r630_to_laptop_cache()
    print("SYNC RESULT:", json.dumps(res, ensure_ascii=False))
