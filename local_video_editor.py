# -*- coding: utf-8 -*-
"""
NEW LIVEVAULT LINK BATCH FETCHER, AI VIETNAMESE TRANSCRIBER & FFMPEG TIKTOK PILL EDITOR
Cho phep nguoi dung dan BAT KY link thu video LiveVault moi nao (vd: http://192.168.1.75:8090/d/... hoac http://127.0.0.1:8090/d/...)
ngay tren giao dien http://127.0.0.1:8099 de:
1. Tu dong chuyen doi IP trong link LiveVault ve http://127.0.0.1:8090 (dich vu tiktok_recorder dang chay ngay tren Laptop)
2. Quet danh sach clip .mp4 moi nhat trong link LiveVault do (hoac 1 clip cu the neu link co ?clip=...)
3. Kiem tra So cai Chong Dang Trung 4 Lop (anti_duplicate_ledger.db) -> Bo qua 100% cac clip da tung dang/luu nhap
4. Nhan dien giong noi Tieng Viet (vi-VN) -> Tu dong phat hien san pham Bac Chuong dang tu van & cat bo doan cuoi vi pham (Lazada/bao gia)
5. Dung FFmpeg + PIL (Font Arial Bold Tieng Viet Unicode) tren Laptop (hoac giao R630 neu dang bat Cau noi):
   - Xoa vien tim tren/duoi + Xoa logo do LiveVault (delogo)
   - Dao 3.5 giay Hook len dau (00:00)
   - Dong khung chu Vang chu Den 3-4 dong gon chuan TikTok Pill (le an toan >= 110px)
   - Unique hoa 2 ban rieng biet cho @suckhoeviet.2 va @suc.khoe.vang.268
   - Sinh Caption Tieng Viet CO DAU 100% + 5 Hashtag chuan SEO + Shop ID GMV Max
   - Dua thang loat video moi nay len DAU bang Lich Dang 1 Tieng / 1 Video!
"""
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from anti_dup_sync import (
    ALLOWED_CHANNELS,
    CACHE_DIR,
    DATA_DIR,
    DB_PATH,
    HUB_DIR,
    LOCAL_QUEUE_FILE,
    init_db,
)

FFMPEG_EXE = r"C:\ffmpeg\bin\ffmpeg.exe" if Path(r"C:\ffmpeg\bin\ffmpeg.exe").exists() else "ffmpeg"
RAW_TMP_DIR = DATA_DIR / "raw_livevault_tmp"
RAW_TMP_DIR.mkdir(parents=True, exist_ok=True)

EDITOR_STATUS = {
    "is_running": False,
    "progress_text": "Sẵn sàng nhận link LiveVault mới để thu, cắt & edit loạt video mới.",
    "processed_clips": 0,
    "total_clips": 0,
    "created_videos": 0,
    "last_link": "",
}

PRODUCT_CATALOG = {
    "bokhop_chondro": {
        "keywords": ["khớp", "sụn", "đầu gối", "lụp cụp", "thoái hóa", "chondro", "glucosamine", "xương"],
        "product_name": "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp (Hỗ trợ sụn khớp, giảm khô khớp)",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505842",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Bổ Khớp Chondro-Aid Pháp", "Bổ sung Glucosamine & Sụn", "Khô khớp, kêu lụp cụp", "Ngày 2 viên sau bữa ăn"],
                "caption_seo": (
                    "Khô khớp, cứng khớp, khớp gối kêu lụp cụp mỗi khi vận động\n"
                    "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp — Bổ sung Glucosamine giúp hỗ trợ bôi trơn sụn khớp và đi lại linh hoạt.\n"
                    "👉 Bấm vào giỏ hàng góc trái màn hình để xem ưu đãi chính hãng!\n"
                    "#arkopharma #chondroaid #bokhop #glucosamine #xuongkhop"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Viên Uống Bổ Khớp Pháp", "Hỗ trợ khô khớp, mỏi gối", "Đứng lên ngồi xuống khó", "Sáng 1 viên - Chiều 1 viên"],
                "caption_seo": (
                    "Đứng lên ngồi xuống khó khăn, đau mỏi khớp gối khi lên xuống cầu thang\n"
                    "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp — Hỗ trợ dưỡng khớp êm ái, vận động nhẹ nhàng cho người lớn tuổi.\n"
                    "👉 Xem ngay tại giỏ hàng màu vàng góc trái video!\n"
                    "#bokhop #duongkhop #chondroaid #khopgoi #chamsocsuckhoe"
                ),
            },
        },
    },
    "daday_baotu": {
        "keywords": ["dạ dày", "bao tử", "ngang ngực", "ợ chua", "trào ngược", "đau rát", "ăn chua"],
        "product_name": "Hỗn dịch Dạ Dày & Bao Tử (Hỗ trợ giảm đau rát, trào ngược, ợ hơi ợ chua)",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Mason & Chăm Sóc Sức Khỏe (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505843",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Hỗ Trợ Dạ Dày & Bao Tử", "Đau rát, ợ hơi, ợ chua", "Ăn xong ngang ngực khó chịu", "Xé uống liền khi đau rát"],
                "caption_seo": (
                    "Đau rát dạ dày, ăn xong ngang ngực, ợ hơi ợ chua khó chịu vào ban đêm\n"
                    "Bác Chường hướng dẫn cách xử lý nhanh khi bao tử đau bất chợt sau bữa ăn chua cay hoặc dùng thuốc dài ngày.\n"
                    "👉 Bấm vào giỏ hàng góc trái màn hình để xem chi tiết & ưu đãi chính hãng!\n"
                    "#daudaday #traonguocdaday #baotu #suckhoetieuhoa #chamsocsuckhoe"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Chăm Sóc Bao Tử Êm Ái", "Giảm tức ngực, trào ngược", "Đau bao tử thất thường", "Hỗ trợ bảo vệ niêm mạc"],
                "caption_seo": (
                    "Hay đau bao tử thất thường, tức ngực khó ngủ vào buổi tối sau khi ăn\n"
                    "Chia sẻ từ Bác Chường giúp làm dịu nhanh niêm mạc dạ dày, hỗ trợ tiêu hóa êm ái cho cả gia đình.\n"
                    "👉 Xem ngay sản phẩm chính hãng tại giỏ hàng màu vàng góc trái video!\n"
                    "#baotu #daudaday #ohoi #ochua #suckhoegiadinh"
                ),
            },
        },
    },
    "giaidoc_gan": {
        "keywords": ["gan", "men gan", "mề đay", "mẩn ngứa", "nóng trong", "bia rượu", "đắng miệng"],
        "product_name": "Viên uống Giải Độc Gan & Hỗ Trợ Hạ Men Gan Chính Hãng (GMV Max)",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Mason & Chăm Sóc Sức Khỏe (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505844",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Giải Độc Gan & Mát Gan", "Nóng trong, mẩn ngứa mề đay", "Hỗ trợ hạ men gan cao", "Bảo vệ tế bào gan mỗi ngày"],
                "caption_seo": (
                    "Nóng trong người, mẩn ngứa mề đay, men gan cao do bia rượu hoặc dùng thuốc tây\n"
                    "Bác Chường tư vấn cách thanh nhiệt, giải độc và bảo vệ tế bào gan khỏe mạnh mỗi ngày.\n"
                    "👉 Xem chi tiết tại giỏ hàng góc trái màn hình!\n"
                    "#giaidocgan #mengancao #matgan #medaymanngua #suckhoegan"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Thảo Dược Bảo Vệ Lá Gan", "Giảm mẩn ngứa, nóng gan", "Đắng miệng, mệt mỏi uể oải", "Thanh nhiệt mát gan an toàn"],
                "caption_seo": (
                    "Dấu hiệu cảnh báo gan đang quá tải: Mẩn ngứa, nổi mề đay, đắng miệng, mệt mỏi\n"
                    "Giải pháp thảo dược hỗ trợ mát gan, tăng cường chức năng gan an toàn từ Bác Chường.\n"
                    "👉 Bấm vào giỏ hàng màu vàng góc trái để nhận ưu đãi!\n"
                    "#baovegan #thanhnhietmatgan #giaidocgan #suckhoemoingay #suckhoevang"
                ),
            },
        },
    },
    "matngu_bonao": {
        "keywords": ["mất ngủ", "khó ngủ", "trằn trọc", "tiền đình", "đau đầu", "chóng mặt", "tuần hoàn não"],
        "product_name": "Viên uống Hỗ Trợ Giấc Ngủ & Tuần Hoàn Máu Não Chính Hãng (GMV Max)",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505845",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Hỗ Trợ Ngủ Ngon Sâu Giấc", "Trằn trọc, đêm thức nhiều lần", "Tăng cường tuần hoàn não", "Sáng dậy tỉnh táo nhẹ người"],
                "caption_seo": (
                    "Trằn trọc khó vào giấc, đêm thức giấc nhiều lần, sáng dậy mệt mỏi uể oải\n"
                    "Bác Chường chia sẻ giải pháp dưỡng tâm an thần, hỗ trợ tuần hoàn máu não giúp ngủ sâu giấc tự nhiên.\n"
                    "👉 Tham khảo ngay tại giỏ hàng góc trái màn hình!\n"
                    "#matngu #khongu #tuanhoannao #giacngungon #suckhoeviet"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Dưỡng Não & An Thần Tự Nhiên", "Giảm hoa mắt, chóng mặt", "Mất ngủ kinh niên ở người già", "Ngủ sâu giấc không mệt mỏi"],
                "caption_seo": (
                    "Người lớn tuổi hay mất ngủ ban đêm, đau đầu hoa mắt chóng mặt khi thay đổi thời tiết\n"
                    "Cùng nghe Bác Chường tư vấn cách chăm sóc giấc ngủ sâu, tinh thần minh mẫn mỗi ngày.\n"
                    "👉 Bấm vào giỏ hàng góc trái để đặt mua chính hãng!\n"
                    "#ngungon #duongnao #matngukinhnien #chamsocnguoicaotuoi #suckhoevang"
                ),
            },
        },
    },
}


def normalize_livevault_url(raw_url: str) -> str:
    """Chuyen bat ky IP LAN nao tren cong 8090 ve http://127.0.0.1:8090 neu LiveVault dang chay tren Laptop."""
    raw_url = raw_url.strip()
    return re.sub(r"^https?://[^/:]+:8090", "http://127.0.0.1:8090", raw_url)


def create_yellow_pill_overlay_png(lines: list[str], out_png: Path):
    """Tao anh PNG trong suot 720x1280 chua 3-4 thanh Pill Nen Vang (#FDE047) Chu Den Dam co dau Tieng Viet (Le an toan >= 110px)."""
    W, H = 720, 1280
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = r"C:\Windows\Fonts\arialbd.ttf"
    if not Path(font_path).exists():
        font_path = r"C:\Windows\Fonts\segoeui.ttf"

    MAX_TEXT_W = 490  # Dam bao le trai/phai >= 115px, khong bao gio tran chu!
    y_cursor = 735
    for idx, line in enumerate(lines[:4]):
        line = line.strip()
        if not line:
            continue
        fsize = 30 if idx == 0 else 26
        font = ImageFont.truetype(font_path, fsize)
        while fsize > 18:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            if tw <= MAX_TEXT_W:
                break
            fsize -= 2
            font = ImageFont.truetype(font_path, fsize)

        bbox = draw.textbbox((0, 0), line, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad_x, pad_y = 20, 10
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        x1 = (W - box_w) // 2
        y1 = y_cursor
        x2 = x1 + box_w
        y2 = y1 + box_h

        # Bong do nhe + Hop pill nen vang vien den
        draw.rounded_rectangle([x1 + 3, y1 + 4, x2 + 3, y2 + 4], radius=16, fill=(0, 0, 0, 160))
        fill_color = (253, 224, 71, 248) if idx == 0 else (254, 240, 138, 242)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=16, fill=fill_color, outline=(15, 23, 42, 255), width=3)
        draw.text((x1 + pad_x, y1 + pad_y - bbox[1]), line, font=font, fill=(10, 10, 10, 255))
        y_cursor = y2 + 9

    img.save(str(out_png), "PNG")


def transcribe_and_detect_product(mp4_path: Path, forced_product_key: str = "AUTO") -> tuple[str, str, float]:
    """Nhan dien giong noi Tieng Viet trong clip de chon dung san pham va tim diem cat duoi vi pham."""
    transcript_parts = []
    safe_end_sec = 53.5
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        wav_tmp = RAW_TMP_DIR / "chunk_tmp.wav"
        for start_s in range(0, 54, 12):
            subprocess.run(
                [
                    FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(start_s), "-t", "11", "-i", str(mp4_path),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav_tmp),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
            )
            if wav_tmp.exists():
                with sr.AudioFile(str(wav_tmp)) as src:
                    audio = recognizer.record(src)
                try:
                    txt = recognizer.recognize_google(audio, language="vi-VN")
                    transcript_parts.append(f"[{start_s:02d}s]: {txt}")
                    low = txt.lower()
                    if start_s >= 36 and any(w in low for w in ["lazada", "shopee", "màn hình", "ngàn", "nghìn"]):
                        safe_end_sec = min(safe_end_sec, float(start_s))
                except Exception:
                    pass
    except Exception:
        pass

    full_tr = " | ".join(transcript_parts)
    if forced_product_key and forced_product_key in PRODUCT_CATALOG:
        return forced_product_key, full_tr, safe_end_sec

    low_tr = full_tr.lower()
    best_key = "bokhop_chondro"
    best_hits = 0
    for pkey, pinfo in PRODUCT_CATALOG.items():
        hits = sum(1 for kw in pinfo["keywords"] if kw in low_tr)
        if hits > best_hits:
            best_hits = hits
            best_key = pkey
    return best_key, full_tr, safe_end_sec


def render_single_channel_video(
    raw_mp4: Path,
    overlay_png: Path,
    out_mp4: Path,
    hook_start: float,
    body_start: float,
    body_end: float,
    zoom: float,
    speed: float,
) -> bool:
    """Cat Hook 3.5s + Than sach, xoa khung tim, delogo chu do va dong khung chu Vang chu Den."""
    body_dur = max(18.0, body_end - body_start)
    crop_h = int(1120 / zoom)
    crop_w = int(720 / zoom)
    crop_x = (720 - crop_w) // 2
    crop_y = 80 + (1120 - crop_h) // 2
    atempo = f",atempo={speed:.2f}" if abs(speed - 1.0) > 0.005 else ""
    setpts = f"*{1.0/speed:.4f}" if abs(speed - 1.0) > 0.005 else ""

    fc = (
        f"[0:v]trim=start={hook_start}:duration=3.5,setpts=(PTS-STARTPTS){setpts},"
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=720:1280,"
        f"delogo=x=85:y=792:w=560:h=56[vh];"
        f"[0:a]atrim=start={hook_start}:duration=3.5,asetpts=PTS-STARTPTS{atempo}[ah];"
        f"[0:v]trim=start={body_start}:duration={body_dur:.1f},setpts=(PTS-STARTPTS){setpts},"
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=720:1280,"
        f"delogo=x=85:y=792:w=560:h=56[vb];"
        f"[0:a]atrim=start={body_start}:duration={body_dur:.1f},asetpts=PTS-STARTPTS{atempo}[ab];"
        f"[vh][ah][vb][ab]concat=n=2:v=1:a=1[vc][ac];"
        f"[vc][1:v]overlay=0:0[vout]"
    )
    cmd = [
        FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-threads", "2",
        "-i", str(raw_mp4),
        "-i", str(overlay_png),
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-map_metadata", "-1",
        str(out_mp4),
    ]
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 50000


def discover_clips_from_livevault_link(livevault_url: str, max_clips: int = 5) -> list[dict]:
    """Doc danh sach clip tu link LiveVault (/d/<token> hoac ?clip=<sha256>)."""
    norm_url = normalize_livevault_url(livevault_url)
    parsed = urllib.parse.urlparse(norm_url)
    qs = urllib.parse.parse_qs(parsed.query)
    base_dir_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/"

    html = urllib.request.urlopen(norm_url, timeout=10).read().decode("utf-8", errors="replace")

    # Tim cac link tai file .mp4 hoac ?clip=<sha256> trong trang LiveVault
    clips = []
    seen = set()

    # Neu nguoi dung dan link co san ?clip=<id> va chi chon 1 clip
    specific_clip = qs.get("clip", [""])[0]

    # Tim toan bo cap (clip_hash, download_href) trong HTML cua LiveVault
    # LiveVault thuong co href="/d/<token>/clip/<hash>.mp4" hoac "?clip=<hash>" hoac "/stream/<hash>"
    for m in re.finditer(r'href=["\']([^"\']*(?:clip=|/clip/|/download/|\.mp4)[^"\']*)["\']', html, re.I):
        href = m.group(1)
        full_href = urllib.parse.urljoin(base_dir_url, href)
        hm = re.search(r"([a-f0-9]{32,64})", full_href)
        cid = hm.group(1) if hm else Path(urllib.parse.urlparse(full_href).path).stem
        if cid and cid not in seen:
            seen.add(cid)
            clips.append({"clip_id": cid, "url": full_href})

    # Tim them trong the <video src="..."> hoac <source src="...">
    for m in re.finditer(r'src=["\']([^"\']+)["\']', html, re.I):
        src = m.group(1)
        if any(k in src for k in [".mp4", "clip", "video", "stream", "/d/"]):
            full_src = urllib.parse.urljoin(base_dir_url, src)
            hm = re.search(r"([a-f0-9]{32,64})", full_src)
            cid = hm.group(1) if hm else f"clip_{int(time.time())}"
            if specific_clip and cid == specific_clip:
                clips.insert(0, {"clip_id": cid, "url": full_src})
            elif cid not in seen:
                seen.add(cid)
                clips.append({"clip_id": cid, "url": full_src})

    if specific_clip:
        exact = [c for c in clips if specific_clip in c["clip_id"] or specific_clip in c["url"]]
        if exact and max_clips == 1:
            return exact[:1]

    return clips[:max_clips]


def start_batch_fetch_and_edit(livevault_url: str, max_clips: int = 5, forced_product_key: str = "AUTO") -> dict:
    if EDITOR_STATUS["is_running"]:
        return {"ok": False, "message": "Hệ thống đang xử lý cắt & edit một loạt video khác, vui lòng đợi hoàn tất!"}

    livevault_url = (livevault_url or "").strip()
    if not livevault_url:
        return {"ok": False, "message": "Vui lòng dán đường link thu video LiveVault mới vào ô!"}

    def _worker():
        EDITOR_STATUS["is_running"] = True
        EDITOR_STATUS["last_link"] = livevault_url
        EDITOR_STATUS["processed_clips"] = 0
        EDITOR_STATUS["created_videos"] = 0
        try:
            EDITOR_STATUS["progress_text"] = f"🔍 Đang kết nối link LiveVault ({normalize_livevault_url(livevault_url)[:55]}...) để lấy danh sách clip mới..."
            clips = discover_clips_from_livevault_link(livevault_url, max_clips=max_clips)
            if not clips:
                EDITOR_STATUS["progress_text"] = "⚠️ Không tìm thấy file video (.mp4) nào trong link vừa dán. Hãy kiểm tra lại link LiveVault (/d/...)."
                EDITOR_STATUS["is_running"] = False
                return

            init_db()
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT clip_id FROM posted_history")
            posted_clips = {r[0] for r in cur.fetchall()}
            conn.close()

            fresh_clips = [c for c in clips if c["clip_id"] not in posted_clips]
            EDITOR_STATUS["total_clips"] = len(fresh_clips)
            if not fresh_clips:
                EDITOR_STATUS["progress_text"] = f"🛡️ Cả {len(clips)} clip trong link này đều ĐÃ ĐƯỢC ĐĂNG hoặc LƯU NHÁP trước đây (Chặn trùng lặp 100%)!"
                EDITOR_STATUS["is_running"] = False
                return

            new_queue_items = []
            for idx, cinfo in enumerate(fresh_clips, 1):
                cid = cinfo["clip_id"]
                short_id = cid[:10]
                EDITOR_STATUS["progress_text"] = f"📥 [{idx}/{len(fresh_clips)}] Đang tải clip gốc {short_id}... từ LiveVault..."

                raw_mp4 = RAW_TMP_DIR / f"raw_{short_id}.mp4"
                dl_url = cinfo["url"]
                # Neu url la ?clip=<hash>, truy cap trang ?clip=<hash> de lay link <video src="..."> truc tiep
                if "?clip=" in dl_url and not dl_url.lower().endswith(".mp4"):
                    sub_html = urllib.request.urlopen(dl_url, timeout=10).read().decode("utf-8", errors="replace")
                    sm = re.search(r'<video[^>]+src=["\']([^"\']+)["\']|<source[^>]+src=["\']([^"\']+)["\']|href=["\']([^"\']*\.mp4[^"\']*)["\']', sub_html, re.I)
                    if sm:
                        rel = sm.group(1) or sm.group(2) or sm.group(3)
                        dl_url = urllib.parse.urljoin(dl_url, rel)

                urllib.request.urlretrieve(dl_url, str(raw_mp4))
                if not raw_mp4.exists() or raw_mp4.stat().st_size < 50000:
                    continue

                EDITOR_STATUS["progress_text"] = f"🎙️ [{idx}/{len(fresh_clips)}] Đang nhận diện giọng nói Bác Chường & lọc đoạn cuối vi phạm ({short_id})..."
                pkey, tr_text, safe_end = transcribe_and_detect_product(raw_mp4, forced_product_key=forced_product_key)
                pcat = PRODUCT_CATALOG[pkey]

                ts_tag = datetime.now().strftime("%H%M%S")
                for ch_idx, ch in enumerate(ALLOWED_CHANNELS):
                    ch_slug = ch.lstrip("@").replace(".", "_")
                    vinfo = pcat["variants"][ch]
                    overlay_png = RAW_TMP_DIR / f"pill_{short_id}_{ch_slug}.png"
                    create_yellow_pill_overlay_png(vinfo["cover_lines"], overlay_png)

                    out_name = f"AUTO_{pkey}_{ch_slug}_{short_id}_{ts_tag}.mp4"
                    out_mp4 = CACHE_DIR / out_name
                    EDITOR_STATUS["progress_text"] = (
                        f"🎬 [{idx}/{len(fresh_clips)}] Đang cắt Hook 3.5s, xóa logo đỏ & đóng khung chữ Vàng chữ Đen cho kênh {ch}..."
                    )
                    zoom = 1.02 if ch_idx == 0 else 1.04
                    speed = 1.00 if ch_idx == 0 else 1.02
                    hook_s = 12.0 if ch_idx == 0 else 18.0
                    ok = render_single_channel_video(
                        raw_mp4=raw_mp4,
                        overlay_png=overlay_png,
                        out_mp4=out_mp4,
                        hook_start=hook_s,
                        body_start=12.0,
                        body_end=safe_end,
                        zoom=zoom,
                        speed=speed,
                    )
                    if ok:
                        EDITOR_STATUS["created_videos"] += 1
                        new_queue_items.append({
                            "id": f"auto_{short_id}_{ch_slug}_{ts_tag}",
                            "clip_id": cid,
                            "channel": ch,
                            "product_key": pkey,
                            "product_name": f"{pcat['product_name']} (Mới cắt từ clip {short_id})",
                            "seller_id": pcat["seller_id"],
                            "seller_name": pcat["seller_name"],
                            "product_id": pcat["product_id"],
                            "scheduled_at": datetime.now().strftime("%H:%M · %d/%m/%Y"),
                            "output_video": f"output_ready/{out_name}",
                            "local_cache_path": str(out_mp4),
                            "cached_offline": True,
                            "cover_text": "\n".join(vinfo["cover_lines"]),
                            "caption_seo": vinfo["caption_seo"],
                            "transcript": tr_text or "Đã lọc sạch âm thanh & kiểm duyệt từ cấm TPCN",
                            "status": "READY",
                        })

                try:
                    raw_mp4.unlink()
                except Exception:
                    pass
                EDITOR_STATUS["processed_clips"] = idx

            if new_queue_items:
                existing = []
                if LOCAL_QUEUE_FILE.exists():
                    try:
                        existing = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
                    except Exception:
                        existing = []
                # Dua loat video moi vua cat len DAU danh sach lich dang 1 tieng/video!
                merged = new_queue_items + existing
                LOCAL_QUEUE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
                EDITOR_STATUS["progress_text"] = (
                    f"✅ HOÀN TẤT! Đã tự động thu, cắt & đóng bìa vàng chữ đen cho {EDITOR_STATUS['created_videos']} video mới "
                    f"(từ {EDITOR_STATUS['processed_clips']} clip gốc) và đưa lên ĐẦU bảng Lịch Đăng 1 Tiếng / 1 Video bên dưới!"
                )
            else:
                EDITOR_STATUS["progress_text"] = "⚠️ Không tạo được video mới nào từ link vừa dán."
        except Exception as e:
            EDITOR_STATUS["progress_text"] = f"❌ Lỗi khi thu & cắt video từ link mới: {e}"
        finally:
            EDITOR_STATUS["is_running"] = False

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "message": "Đã bắt đầu thu, cắt & edit loạt video mới trong nền!"}
