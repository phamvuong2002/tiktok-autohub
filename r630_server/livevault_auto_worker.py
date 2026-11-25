# -*- coding: utf-8 -*-
"""
LIVEVAULT 24/7 AUTO-FETCHER, VIETNAMESE SPEECH ANALYZER & 3-CHANNEL CUTTER DAEMON
Chay ngam 24/7 tren Server Dell R630 (Container 240 - 192.168.1.240):
1. Tu dong quet cong LiveVault (http://192.168.1.75:8090/d/.../clips?limit=30&session=current) moi 45 giay
2. Tu dong tai cac video 1 phut moi ve o cung R630 (/opt/tiktok_r630_hub/input_raw/)
3. Tu dong nghe loi thoai tieng Viet tung 6 giay (00s-60s):
   - Nhan dien san pham Bac Chuong dang noi (Canxi, Bo khop, Omega 3, Vitamin Azinc, Collagen, Biotin)
   - Phat hien & cat bo doan nhac Lazada/Shopee/gia tien o cuoi video
   - Tim dung 3.5 giay Hook dat gia nhat (trieu chung dau nhuc / gio hop san pham) day len dau 00:00
4. Tu dong crop bo 2 vien tim + dong hop Vang Chanh chu Den Dam che kin dong chu do 'Dang phat truc tiep...'
5. Tu dong xep lich gian cach vao Kho Du Tru (Content Bank) cho 3 kenh & ban sang Oppo A57 neu ADB Wi-Fi dang bat
"""
import concurrent.futures
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from tpcn_seo_engine import PRODUCT_CATALOG, sanitize_tpcn_text

BASE_DIR = Path("/opt/tiktok_r630_hub")
INPUT_DIR = BASE_DIR / "input_raw"
OUTPUT_DIR = BASE_DIR / "output_ready"
DATA_DIR = BASE_DIR / "data"
OVERLAY_DIR = DATA_DIR / "overlays"
QUEUE_FILE = DATA_DIR / "publish_queue.json"
PROCESSED_FILE = DATA_DIR / "processed_clips.json"
CONFIG_FILE = DATA_DIR / "worker_config.json"
ADB_CONFIG_FILE = DATA_DIR / "oppo_adb.json"

for d in (INPUT_DIR, OUTPUT_DIR, DATA_DIR, OVERLAY_DIR):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_LIVEVAULT_URL = "http://192.168.1.75:8090/d/LTU1NzUwMjQ0OTE6MTc5ODA4ODA3NDoxMWQxMDU3NGMzM2VjYjNkOWY0OTk4ODM5NDM2ZDJmNTBlMTkzZDg3MDdjZGEzMWI4YzFkMTM4Y2JiZmFkYmZi/"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Tu khoa nhan dien san pham tu loi thoai Bac Chuong (bao gom ca tu dong am do Google Speech-to-Text nghe)
PRODUCT_KEYWORDS = {
    "marial_gel": [
        "marial", "mi đen", "mang gen", "malaysia", "dạ dày", "bao tử", "trào ngược",
        "ợ chua", "ợ hơi", "ngang ngực", "tức ngực", "xé uống liền", "xé ra uống",
        "đồ chua", "đồ cay", "viêm xung huyết", "nóng rát cổ họng", "niêm mạc dạ dày", "thuốc giảm đau",
    ],
    "ginkgo_bonao": [
        "ginkgo", "ganko", "bổ não", "dưỡng não", "tiền đình", "rối loạn tiền đình",
        "tuần hoàn não", "tuần hoàn máu não", "thiểu năng tuần hoàn", "hoa mắt", "chóng mặt",
        "ù tai", "đau nửa bên đầu", "đỉnh đầu", "60 viên mình uống được 2 tháng",
    ],
    "canxi_mason": [
        "canxi", "green canxi", "canxi rau củ", "citrat", "citrate", "tắm nắng", "uống sữa",
        "loãng xương", "chuột rút", "vọp bẻ", "tụt canxi", "canxi hữu cơ",
    ],
    "bokhop_chondro": [
        "bổ khớp", "sụn khớp", "glucosamine", "glucosamin", "khớp gối", "khớp háng",
        "teo cơ", "lụp cụp", "vịn bàn", "vịn tường", "tràn dịch", "viêm khớp",
    ],
    "omega3_arko": [
        "omega", "dầu cá", "mỡ máu", "máu nhiễm mỡ", "huyết áp", "tim mạch",
        "khô mắt", "giác mạc", "dha", "epa", "gan nhiễm mỡ", "tê châm chích",
    ],
    "vitamin_azinc": [
        "vitamin tổng hợp", "azinc", "adc", "khoáng chất", "đề kháng", "suy nhược",
        "uể oải", "kén ăn", "ăn chay", "12 vitamin", "8 loại khoáng", "8 khoáng chất",
        "20 chất", "120 viên", "3b", "b1 b6 b12", "thiếu máu", "thiếu sắt", "dây thần kinh tọa",
    ],
    "collagen_chalpha": ["collagen", "ống uống", "tầm xuân", "nhập khẩu đức", "dạng nước", "ch-alpha"],
    "biotin_forcapil": [
        "rụng tóc", "mọc tóc", "biotin", "forcapil", "for cabin", "ford cabin",
        "dưỡng tóc", "mái tóc", "tóc con", "tóc yếu", "tóc khô", "gãy rụng", "hói",
    ],
}

# Tu khoa cam o cuoi clip can cat bo ngay (Lazada, Shopee, bao gia tien, khoe man hinh gio hang)
FORBIDDEN_TAIL_WORDS = ["lazada", "shopee", "tiki", "sendo", "500 rưỡi", "trăm rưỡi", "400 mấy", "giảm 18%", "giảm 20%", "chuyển khoản", "trên màn hình", "bấm vào giỏ"]

# Tu khoa Hook trieu chung manh de uu tien chon 3.5s mo dau
HOOK_PAIN_WORDS = ["teo cơ", "nhức lưng", "khó ngủ", "tê tay", "chuột rút", "rụng tóc", "đau nhức", "khô khớp", "lụp cụp", "mệt mỏi", "mỡ máu", "vịn tường", "tụt canxi"]


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def get_worker_config() -> dict:
    cfg = load_json(CONFIG_FILE, {})
    if "livevault_url" not in cfg:
        cfg["livevault_url"] = DEFAULT_LIVEVAULT_URL
    if "auto_poll" not in cfg:
        cfg["auto_poll"] = True
    if "poll_interval_sec" not in cfg:
        cfg["poll_interval_sec"] = 45
    if "auto_adb_push" not in cfg:
        cfg["auto_adb_push"] = True
    if "max_clips_per_cycle" not in cfg:
        cfg["max_clips_per_cycle"] = 2
    save_json(CONFIG_FILE, cfg)
    return cfg


def transcribe_60s_video(mp4_path: Path) -> list[dict]:
    """Chia video 60s thanh 10 doan 6s va nhan dien giong noi tieng Viet song song."""
    import speech_recognition as sr
    tmp_dir = DATA_DIR / "tmp_wav"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    def worker(idx: int) -> dict:
        start = idx * 6
        wav = tmp_dir / f"{mp4_path.stem}_{start:02d}.wav"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", "6.3", "-i", str(mp4_path), "-ac", "1", "-ar", "16000", str(wav)],
            check=False,
            capture_output=True,
        )
        txt = ""
        if wav.exists():
            rec = sr.Recognizer()
            try:
                with sr.AudioFile(str(wav)) as src:
                    aud = rec.record(src)
                txt = rec.recognize_google(aud, language="vi-VN")
            except Exception:
                txt = ""
            wav.unlink(missing_ok=True)
        return {"start": start, "end": start + 6, "text": txt.strip()}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        segments = list(ex.map(worker, range(10)))
    return segments


def analyze_segments(segments: list[dict]) -> dict:
    """
    Tu loi thoai 10 doan 6s:
    1. Xac dinh san pham (product_key)
    2. Tim diem cat cuoi (body_end) de loai bo Lazada / bao gia tien
    3. Tim diem bat dau than chinh (body_start) bo qua 6-12s dau bi cut cau
    4. Tim 3.5s Hook dat gia nhat cho 3 kenh
    """
    full_text = " ".join(s["text"].lower() for s in segments)

    # 1. Detect product
    scores = {k: 0 for k in PRODUCT_KEYWORDS}
    for pkey, kw_list in PRODUCT_KEYWORDS.items():
        for kw in kw_list:
            if kw in full_text:
                scores[pkey] += full_text.count(kw) * (2 if len(kw) > 6 else 1)

    best_product = max(scores, key=scores.get)
    if scores[best_product] == 0:
        # Neu khong nghe ro tu khoa san pham cu the, bo qua clip (tranh gan nham sang Xương Khớp!)
        return {"valid": False, "reason": "Không khớp từ khóa sản phẩm nào trong danh mục (tránh gán nhầm sản phẩm)"}

    # 2. Detect forbidden tail (Lazada / Shopee / price at >= 36s)
    body_end = 54.0
    cut_reasons = []
    for s in segments:
        if s["start"] >= 36:
            low = s["text"].lower()
            for bad in FORBIDDEN_TAIL_WORDS:
                if bad in low:
                    body_end = min(body_end, float(s["start"]))
                    cut_reasons.append(f"Đã cắt bỏ đoạn [{s['start']}s-60s] chứa '{bad}'")
                    break

    # 3. Choose clean body_start (skip first 6-12s incomplete sentence if middle is rich)
    body_start = 12.0 if body_end >= 44.0 else 6.0
    body_dur = max(26.0, round(body_end - body_start, 1))

    # 4. Score segments for 3.5s Hook (tranh chon doan giơ dien thoai khoe gio hang)
    ranked_hooks = []
    for s in segments:
        if s["start"] >= body_end:
            continue
        low = s["text"].lower()
        if any(bad in low for bad in ["màn hình", "giỏ hàng", "lazada", "shopee", "trăm", "ngàn"]):
            continue
        sc = sum(3 for pw in HOOK_PAIN_WORDS if pw in low) + (2 if 12 <= s["start"] <= 36 else 0)
        ranked_hooks.append((sc, float(s["start"]), s["text"]))
    ranked_hooks.sort(key=lambda x: (-x[0], x[1]))

    h1 = ranked_hooks[0][1] if len(ranked_hooks) > 0 else 18.0
    h2 = ranked_hooks[1][1] if len(ranked_hooks) > 1 else min(body_end - 4.0, 36.0)
    h3 = ranked_hooks[2][1] if len(ranked_hooks) > 2 else 12.0

    return {
        "valid": True,
        "product_key": best_product,
        "body_start": body_start,
        "body_dur": body_dur,
        "hooks": [h1, h2, h3],
        "cut_reasons": cut_reasons,
        "transcript_summary": " | ".join(f"[{s['start']:02d}s]: {s['text']}" for s in segments if s["text"]),
    }


def make_yellow_banner_png(text_lines: str, out_png: Path, width: int = 720, height: int = 1280):
    """
    Thiet ke ghi chu tren video DUNG CHUAN TikTok Native Highlight cua @baovesuckhoe2424 & @phongbenhthayvichuabenh:
    - 3-4 dong cuc ngan, can giua, moi dong la 1 dai pill nen vang chanh (#FDE047) bo tron om sat chu
    - Gioi han chieu rong an toan MAX_W = 520px tren khung 720px (chua le an toan >= 100px moi ben,
      tu dong co font neu dong dai -> TUYET DOI KHONG BAO GIO TRAN RA KHOI VIDEO hay bi cat tren luoi 3 cot!)
    - Lop nen vang trung tam che kin 100% dong chu do 'Dang phat truc tiep ngay...'
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    raw_lines = [ln.strip() for ln in text_lines.strip().splitlines() if ln.strip()]

    # Tu dong ngat dong neu co dong nao > 26 ky tu
    lines = []
    for ln in raw_lines:
        if len(ln) <= 26:
            lines.append(ln)
        else:
            words = ln.split()
            mid = len(words) // 2
            lines.append(" ".join(words[:mid]))
            lines.append(" ".join(words[mid:]))
    lines = lines[:4]

    MAX_TEXT_W = 500  # Chua le an toan 110px moi ben tren khung 720px!
    line_Layouts = []
    for ln in lines:
        fsize = 27
        font = ImageFont.truetype(FONT_BOLD, fsize)
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        while tw > MAX_TEXT_W and fsize > 18:
            fsize -= 1
            font = ImageFont.truetype(FONT_BOLD, fsize)
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        line_Layouts.append((ln, font, tw, th))

    row_h = 44
    total_h = len(line_Layouts) * row_h
    base_y = 748 - (total_h // 2)

    # Ve tung dai pill highlight om sat tung dong chu (hieu ung bac thang TikTok Native sach 100%, khong vien den)
    cur_y = base_y
    for ln, font, tw, th in line_Layouts:
        pill_w = tw + 34
        px1 = (width - pill_w) // 2
        px2 = px1 + pill_w
        py1 = cur_y - 3
        py2 = cur_y + row_h + 1
        draw.rounded_rectangle([px1, py1, px2, py2], radius=12, fill=(253, 224, 71, 255))
        tx = (width - tw) // 2
        ty = cur_y + (row_h - th) // 2 - 3
        draw.text((tx, ty), ln, font=font, fill=(15, 23, 42, 255))
        cur_y += row_h

    img.save(str(out_png), "PNG")


def render_smart_clip(src_mp4: Path, dst_mp4: Path, banner_png: Path, hook_start: float, hook_dur: float, body_start: float, body_dur: float, zoom: float, speed: float):
    pts = round(1.0 / speed, 4)
    crop_w = round(1.0 / zoom, 4)
    crop_h = round(0.91 / zoom, 4)
    fc = (
        f"[0:v]trim=start={hook_start}:duration={hook_dur},setpts=PTS-STARTPTS[hv];"
        f"[0:a]atrim=start={hook_start}:duration={hook_dur},asetpts=PTS-STARTPTS[ha];"
        f"[0:v]trim=start={body_start}:duration={body_dur},setpts=PTS-STARTPTS[bv];"
        f"[0:a]atrim=start={body_start}:duration={body_dur},asetpts=PTS-STARTPTS[ba];"
        f"[hv][ha][bv][ba]concat=n=2:v=1:a=1[cv][ca];"
        f"[cv]setpts={pts}*PTS,crop=iw*{crop_w}:ih*{crop_h},scale=720:1280,"
        f"delogo=x=85:y=792:w=560:h=56,"
        f"eq=brightness=0.015:saturation=1.04:contrast=1.02[vbase];"
        f"[vbase][1:v]overlay=0:0[vout];"
        f"[ca]atempo={speed}[aout]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src_mp4), "-i", str(banner_png),
        "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", "30", "-b:v", "3500k", "-c:a", "aac", "-b:a", "128k",
        "-map_metadata", "-1", "-movflags", "+faststart", str(dst_mp4),
    ]
    subprocess.run(cmd, check=True)


def next_golden_schedule_slot(channel: str, existing_queue: list[dict]) -> str:
    """Tinh khung gio gian cach DUNG 1 TIENG / 1 VIDEO (60 phut/bai tren cung kenh) de dung dan."""
    ch_items = [x for x in existing_queue if x.get("channel") == channel and x.get("status") != "POSTED"]
    offset_min = (len(ch_items) + 1) * 60
    return (datetime.now() + timedelta(minutes=offset_min)).strftime("%H:%M · %d/%m/%Y")


def process_single_livevault_clip(clip_meta: dict, lv_base_url: str) -> list[dict]:
    clip_id = clip_meta["id"]
    clip_name = clip_meta["name"]
    src_mp4 = INPUT_DIR / clip_name

    if not src_mp4.exists() or src_mp4.stat().st_size < 100000:
        dl_url = f"{lv_base_url.rstrip('/')}/file/{clip_id}.mp4"
        urllib.request.urlretrieve(dl_url, str(src_mp4))

    segments = transcribe_60s_video(src_mp4)
    analysis = analyze_segments(segments)
    if not analysis["valid"]:
        return []

    pkey = analysis["product_key"]
    prod = PRODUCT_CATALOG[pkey]
    queue = load_json(QUEUE_FILE, [])
    now = datetime.now()

    channels_cfg = [
        {"channel": "@suckhoeviet.2", "space": "Không gian 1 (Chính - Oppo A57)", "zoom": 1.02, "speed": 1.00, "hook_s": analysis["hooks"][0], "hook_d": 3.6},
        {"channel": "@suc.khoe.vang.268", "space": "Không gian 2 (Bản sao hệ thống - Oppo A57)", "zoom": 1.04, "speed": 1.02, "hook_s": analysis["hooks"][1], "hook_d": 3.8},
        {"channel": "kenh_3", "space": "Kênh 3 (TikTok Studio Web R630)", "zoom": 1.03, "speed": 0.99, "hook_s": analysis["hooks"][2], "hook_d": 3.5},
    ]

    created = []
    for idx, ccfg in enumerate(channels_cfg):
        ch = ccfg["channel"]
        ang = prod["angles"][ch]
        raw_cover = "\n".join(ang.get("cover_lines", [ang["symptom"], prod["short_name"], prod["dosage"]]))
        raw_caption = f"{ang['symptom']}\n{prod['name']} — {ang['benefit']}\nCách dùng: {prod['dosage']}\n{' '.join(ang['hashtags'])}"
        clean_cover, f1 = sanitize_tpcn_text(raw_cover)
        clean_caption, f2 = sanitize_tpcn_text(raw_caption)

        ch_slug = ch.replace("@", "").replace(".", "_")
        banner_png = OVERLAY_DIR / f"banner_{clip_id[:8]}_{ch_slug}.png"
        make_yellow_banner_png(clean_cover, banner_png)

        out_name = f"AUTO_{pkey}_{ch_slug}_{clip_name[-9:-4]}_{now.strftime('%H%M%S')}.mp4"
        out_path = OUTPUT_DIR / out_name

        b_start = analysis["body_start"] + (idx * 0.8)
        b_dur = max(25.0, analysis["body_dur"] - (idx * 1.0))

        render_smart_clip(
            src_mp4=src_mp4,
            dst_mp4=out_path,
            banner_png=banner_png,
            hook_start=ccfg["hook_s"],
            hook_dur=ccfg["hook_d"],
            body_start=b_start,
            body_dur=b_dur,
            zoom=ccfg["zoom"],
            speed=ccfg["speed"],
        )

        total_dur = round((ccfg["hook_d"] + b_dur) / ccfg["speed"], 1)
        slot_str = next_golden_schedule_slot(ch, queue + created)

        item = {
            "id": f"auto_{clip_id[:10]}_{ch_slug}",
            "clip_id": clip_id,
            "channel": ch,
            "phone_space": ccfg["space"],
            "product_key": pkey,
            "product_name": f"{prod['name']} (Tự cắt từ {clip_name})",
            "seller_id": prod["seller_id"],
            "seller_name": prod["seller_name"],
            "product_id": prod["product_id"],
            "scheduled_at": slot_str,
            "source_video": f"input_raw/{clip_name} (Hook {ccfg['hook_s']}s + Thân {b_start}s..{round(b_start+b_dur,1)}s)",
            "output_video": f"output_ready/{out_name}",
            "clip_start_sec": int(b_start),
            "clip_duration_sec": total_dur,
            "unique_profile": {"zoom": ccfg["zoom"], "speed": ccfg["speed"], "strip_metadata": True},
            "cover_text": clean_cover,
            "caption_seo": clean_caption,
            "hashtags": ang["hashtags"],
            "seo_score": 100,
            "transcript": analysis["transcript_summary"],
            "policy_fixes": ["Tự che chữ đỏ LiveVault bằng hộp vàng chữ đen", "Tự crop 2 viền tím"] + analysis["cut_reasons"] + f1 + f2,
            "status": "READY",
        }
        created.append(item)

        # Auto push via ADB Wi-Fi if Oppo A57 is connected and channel is for Oppo A57
        if ch == "@suckhoeviet.2":
            try:
                r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=4)
                online = [ln.split()[0] for ln in r.stdout.splitlines()[1:] if "\tdevice" in ln]
                if online:
                    remote = f"/sdcard/DCIM/Camera/{out_name}"
                    subprocess.run(["adb", "-s", online[0], "push", str(out_path), remote], capture_output=True, timeout=25)
                    subprocess.run(["adb", "-s", online[0], "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{remote}"], capture_output=True, timeout=5)
            except Exception:
                pass

    queue = created + queue
    save_json(QUEUE_FILE, queue[:90])

    # Mark clip on LiveVault server so everyone sees it was processed
    try:
        mark_url = f"{lv_base_url.rstrip('/')}/marks"
        payload = json.dumps({"id": clip_id, "marked": True, "revision": clip_meta.get("markRevision", 0)}).encode("utf-8")
        req = urllib.request.Request(mark_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass

    return created


def poll_once() -> dict:
    cfg = get_worker_config()
    lv_url = cfg["livevault_url"].split("?")[0]
    if not lv_url.endswith("/"):
        lv_url += "/"

    processed = load_json(PROCESSED_FILE, {})
    api_url = f"{lv_url}clips?limit=25&session=current"
    resp = json.loads(urllib.request.urlopen(api_url, timeout=10).read().decode("utf-8"))
    clips = resp.get("clips", [])

    new_count = 0
    rendered_videos = 0
    for c in clips:
        cid = c["id"]
        if cid in processed:
            continue
        if new_count >= cfg.get("max_clips_per_cycle", 2):
            break
        print(f"[AUTO-WORKER] Phat hien video 1 phut moi tren LiveVault: {c['name']} ({cid[:10]}...)")
        items = process_single_livevault_clip(c, lv_url)
        processed[cid] = {
            "name": c["name"],
            "processed_at": datetime.now().isoformat(),
            "generated_count": len(items),
        }
        save_json(PROCESSED_FILE, processed)
        new_count += 1
        rendered_videos += len(items)

    return {"checked_clips": len(clips), "new_clips_processed": new_count, "rendered_videos": rendered_videos, "total_processed_history": len(processed)}


def run_daemon():
    print("============================================================")
    print(" LIVEVAULT 24/7 AUTO-WORKER DAEMON STARTED ON DELL R630")
    print("============================================================")
    while True:
        try:
            cfg = get_worker_config()
            if cfg.get("auto_poll", True):
                res = poll_once()
                if res["new_clips_processed"] > 0:
                    print(f"[AUTO-WORKER] Da xu ly {res['new_clips_processed']} clip moi -> Sinh {res['rendered_videos']} video chuan SEO!")
        except Exception as e:
            print(f"[AUTO-WORKER WARN] {e}")
        time.sleep(get_worker_config().get("poll_interval_sec", 45))


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        print(json.dumps(poll_once(), ensure_ascii=False))
    else:
        run_daemon()
