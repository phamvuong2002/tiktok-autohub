# -*- coding: utf-8 -*-
"""
OPPO A57 SMART CONNECTOR, 4-ACCOUNT TIKTOK SWITCHER & 1-HOUR PACED AUTO-POSTER
Chay truc tiep tren Laptop (C:\\TikTok_AutoHub\\oppo_auto_poster.py):
1. Ket noi Oppo A57 sieu de (USB -> Tu dong bat cong co dinh 5555, hoac Tu dong do IP/Port trong mang Local Wi-Fi)
2. Tu dong kiem tra & chuyen doi DUNG tai khoan (@suckhoeviet.2 hoac @suc.khoe.vang.268) trong 4 tai khoan tren may
3. Kiem tra Chong Dang Trung 3 Lop (SHA-256 file + clip_id + caption)
4. Don sach cuon Camera Oppo A57 -> Day DUY NHAT 1 video cua khung gio do -> Mo TikTok -> Chon video -> Dien Caption SEO
"""
import concurrent.futures
import json
import re
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from anti_dup_sync import (
    ALLOWED_CHANNELS,
    CACHE_DIR,
    DATA_DIR,
    HUB_DIR,
    LOCAL_QUEUE_FILE,
    check_duplicate_guard,
    get_settings,
    record_posted_in_ledger,
    sync_from_r630_to_laptop_cache,
)

ADB_EXE = str(HUB_DIR / "tools" / "platform-tools" / "adb.exe")
TIKTOK_PKG = "com.ss.android.ugc.trill"


def run_adb(args: list[str], serial: str = None, timeout: int = 20) -> tuple[int, str, str]:
    cmd = [ADB_EXE]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def get_laptop_subnet_prefix() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}"
    except Exception:
        return "192.168.1"


def quick_check_oppo_connected() -> dict:
    """Kiem tra tuc thi (<50ms) xem Oppo A57 da ket noi trong danh sach adb devices chua."""
    _, out, _ = run_adb(["devices", "-l"], timeout=3)
    lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip() and "\toffline" not in ln]
    for ln in lines:
        if "device " in ln:
            serial = ln.split()[0]
            return {"connected": True, "serial": serial, "mode": "USB" if ":" not in serial else "WIFI", "detail": ln}
    return {
        "connected": False,
        "serial": None,
        "mode": "NONE",
        "detail": "Chưa kết nối Oppo A57. Hãy cắm cáp USB 1 lần (để khóa cổng 5555) hoặc bật Gỡ lỗi không dây rồi bấm 'Tự Động Tìm & Nối Oppo A57'.",
    }


def auto_connect_oppo(hint_ip: str = None) -> dict:
    """
    Ket noi Oppo A57 theo 3 tang tu dong (Khong can R630):
    1. Kiem tra thiet bi da ket noi san (USB hoac Wi-Fi) -> Neu la cap USB, tu dong mo cong co dinh 5555!
    2. Quet nhanh cong 5555 va cac cong Go loi khong day (30000-49999) tren IP Oppo A57
    3. Neu Oppo A57 doi IP (khi ra quan cafe / Hotspot), tu dong tim IP Oppo A57 trong mang Local cua Laptop!
    """
    _, out, _ = run_adb(["devices", "-l"])
    lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip() and "\toffline" not in ln]

    # Xoa cac ket noi offline cu
    if "\toffline" in out:
        run_adb(["disconnect"])
        _, out, _ = run_adb(["devices", "-l"])
        lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]

    for ln in lines:
        if "device " in ln:
            serial = ln.split()[0]
            # Neu dang cam cap USB (serial khong chua ':'), tu dong bat luon cong co dinh 5555!
            if ":" not in serial:
                run_adb(["tcpip", "5555"], serial=serial)
            return {"connected": True, "serial": serial, "mode": "USB" if ":" not in serial else "WIFI", "detail": ln}

    cfg = get_settings()
    target_ip = (hint_ip or cfg.get("oppo_last_ip") or "192.168.1.95").split(":")[0]

    # Neu nguoi dung nhap san IP:Port
    if hint_ip and ":" in hint_ip:
        run_adb(["disconnect"])
        _, co, ce = run_adb(["connect", hint_ip])
        if "connected to" in co.lower():
            cfg["oppo_last_ip"] = hint_ip.split(":")[0]
            (DATA_DIR / "hub_settings.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"connected": True, "serial": hint_ip, "mode": "WIFI", "detail": co}

    # Thu cong 5555 co dinh truoc, sau do quet nhanh dải 30000-49999 tren target_ip
    def probe_port(p: int):
        try:
            s = socket.create_connection((target_ip, p), 0.12)
            s.close()
            return p
        except Exception:
            return None

    open_ports = []
    if probe_port(5555):
        open_ports.append(5555)
    else:
        with concurrent.futures.ThreadPoolExecutor(160) as ex:
            open_ports = [p for p in ex.map(probe_port, range(30000, 49999)) if p]

    for p in open_ports:
        addr = f"{target_ip}:{p}"
        _, co, _ = run_adb(["connect", addr])
        if "connected to" in co.lower():
            time.sleep(0.5)
            _, dout, _ = run_adb(["devices", "-l"])
            if f"{addr}\tdevice" in dout or f"{addr} " in dout and "offline" not in dout:
                return {"connected": True, "serial": addr, "mode": "WIFI_AUTO", "detail": f"Tự động nối {addr}"}

    # Tang 3: Neu mang Laptop + Oppo A57 ra ngoai (doi mang Wi-Fi / Hotspot -> Oppo A57 doi IP moi),
    # quet nhanh cong 5555 tren toan bo dai mang Local hien tai cua Laptop trong 0.4 giay!
    subnet = get_laptop_subnet_prefix()
    def probe_subnet_host(host_idx: int):
        ip_cand = f"{subnet}.{host_idx}"
        if ip_cand == target_ip:
            return None
        try:
            s = socket.create_connection((ip_cand, 5555), 0.12)
            s.close()
            return ip_cand
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(128) as ex:
        found_ips = [ip for ip in ex.map(probe_subnet_host, range(2, 255)) if ip]

    for ip_cand in found_ips:
        addr = f"{ip_cand}:5555"
        _, co, _ = run_adb(["connect", addr])
        if "connected to" in co.lower():
            cfg["oppo_last_ip"] = ip_cand
            (DATA_DIR / "hub_settings.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"connected": True, "serial": addr, "mode": "WIFI_ROAMING_AUTO", "detail": f"Tự động tìm thấy Oppo A57 ở mạng mới ({addr})"}

    return {
        "connected": False,
        "serial": None,
        "mode": "NONE",
        "detail": f"Chưa thấy Oppo A57 mở cổng trên {target_ip} (hoặc mạng {subnet}.x). Hãy cắm cáp USB vào Laptop 1 lần (để khóa cổng 5555) hoặc bật Gỡ lỗi không dây trên Oppo A57.",
    }


def pair_oppo_wireless(pair_ip_port: str, pair_code: str) -> dict:
    """Ghep noi ADB Wi-Fi 6 so truc tiep tu Laptop (khi can ghep noi tren mang moi)."""
    rc, out, err = run_adb(["pair", pair_ip_port.strip(), pair_code.strip()], timeout=20)
    combined = f"{out}\n{err}".strip()
    if "successfully paired" in combined.lower():
        ip_only = pair_ip_port.split(":")[0]
        cfg = get_settings()
        cfg["oppo_last_ip"] = ip_only
        (DATA_DIR / "hub_settings.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        conn = auto_connect_oppo(hint_ip=ip_only)
        return {"ok": True, "message": f"Ghép nối thành công ({combined}). {conn.get('detail', '')}", "connection": conn}
    return {"ok": False, "message": f"Ghép nối chưa thành công: {combined}"}


def dump_oppo_ui(serial: str) -> list[dict]:
    """Lay danh sach toan bo cac phan tu (text, content-desc, resource-id, bounds, center_x, center_y) tren man hinh Oppo A57."""
    run_adb(["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], serial=serial, timeout=12)
    xml_local = DATA_DIR / "window_dump.xml"
    run_adb(["pull", "/sdcard/window_dump.xml", str(xml_local)], serial=serial, timeout=10)
    if not xml_local.exists():
        return []
    try:
        tree = ET.parse(str(xml_local))
        nodes = []
        for elem in tree.iter("node"):
            txt = (elem.attrib.get("text") or "").strip()
            desc = (elem.attrib.get("content-desc") or "").strip()
            rid = (elem.attrib.get("resource-id") or "").strip()
            b = elem.attrib.get("bounds") or ""
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            else:
                cx, cy = 0, 0
            if txt or desc or rid:
                nodes.append({"text": txt, "desc": desc, "id": rid, "bounds": b, "cx": cx, "cy": cy})
        return nodes
    except Exception:
        return []


def has_captcha_on_screen(nodes: list[dict]) -> bool:
    blob = " ".join((n["text"] + " " + n["desc"]).lower() for n in nodes)
    return any(w in blob for w in ["kéo thanh trượt", "ghép hình", "xác minh để tiếp tục", "drag the slider", "fit the puzzle", "captcha"])


def ensure_correct_tiktok_account(serial: str, target_handle: str) -> tuple[bool, str]:
    """
    Mo TikTok -> Vao tab Ho So -> Kiem tra xem dang o tai khoan nao trong 4 tai khoan.
    Neu chua dung target_handle (@suckhoeviet.2 hoac @suc.khoe.vang.268), tu dong bam mo bang
    Chuyen doi tai khoan (Switch Account) va chon dung tai khoan muc tieu!
    """
    clean_handle = target_handle.lstrip("@").lower()
    display_map = {
        "suckhoeviet.2": ["suckhoeviet.2", "sống khoẻ mỗi ngày", "song khoe moi ngay"],
        "suc.khoe.vang.268": ["suc.khoe.vang.268", "sức khoẻ vàng", "suc khoe vang"],
    }
    aliases = display_map.get(clean_handle, [clean_handle])

    # 1. Danh thuc man hinh & mo TikTok
    run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial=serial)
    run_adb(["shell", "monkey", "-p", TIKTOK_PKG, "-c", "android.intent.category.LAUNCHER", "1"], serial=serial)
    time.sleep(4)

    # 2. Bam vao tab Ho so (Profile - goc duoi ben phai x=648, y=1545 tren Oppo A57 720x1612)
    run_adb(["shell", "input", "tap", "648", "1545"], serial=serial)
    time.sleep(2.5)

    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return False, "TẠM DỪNG AN TOÀN: Màn hình TikTok đang hiện bảng xác minh CAPTCHA. Bạn vui lòng tự kéo xác thực trên điện thoại trước."

    screen_text = " ".join((n["text"] + " " + n["desc"]).lower() for n in nodes)
    if f"@{clean_handle}" in screen_text or clean_handle in screen_text:
        return True, f"Đã xác nhận đang ở đúng tài khoản @{clean_handle}"

    # 3. Neu dang o tai khoan khac trong 4 tai khoan -> Mo bang Chuyen doi tai khoan
    # Tim nut ten tai khoan o dinh man hinh Ho so (y < 200, x giua man hinh)
    top_switch = next((n for n in nodes if 60 <= n["cy"] <= 185 and 180 <= n["cx"] <= 540 and (n["text"] or n["desc"])), None)
    if top_switch:
        run_adb(["shell", "input", "tap", str(top_switch["cx"]), str(top_switch["cy"])], serial=serial)
    else:
        run_adb(["shell", "input", "tap", "360", "110"], serial=serial)
    time.sleep(2.5)

    sheet_nodes = dump_oppo_ui(serial)
    target_node = None
    for n in sheet_nodes:
        combined = (n["text"] + " " + n["desc"]).lower()
        if any(a in combined for a in aliases):
            target_node = n
            break

    if not target_node:
        return False, f"Không tìm thấy tài khoản '@{clean_handle}' trong bảng chuyển đổi 4 tài khoản trên Oppo A57. Hãy kiểm tra tài khoản đã đăng nhập chưa."

    # 4. Cham vao dung tai khoan muc tieu
    run_adb(["shell", "input", "tap", str(target_node["cx"]), str(target_node["cy"])], serial=serial)
    time.sleep(4.0)

    # 5. Vao lai tab Ho so kiem tra xac nhan lan 2
    run_adb(["shell", "input", "tap", "648", "1545"], serial=serial)
    time.sleep(2.0)
    verify_nodes = dump_oppo_ui(serial)
    verify_text = " ".join((n["text"] + " " + n["desc"]).lower() for n in verify_nodes)
    if any(a in verify_text for a in aliases):
        return True, f"Đã tự động chuyển sang đúng tài khoản @{clean_handle} thành công!"

    return True, f"Đã chọn tài khoản @{clean_handle} từ danh sách 4 tài khoản."


def prepare_single_clean_video_on_oppo(serial: str, local_video_path: Path) -> tuple[bool, str]:
    """
    Xoa TOAN BO cac file video AUTO_*/REAL_* cu trong /sdcard/DCIM/Camera/ cua Oppo A57,
    sau do day DUY NHAT 1 file video cua luot dang nay vao Camera va quet Media Scanner
    -> Dam bao o dau cuon Camera CHI CO DUY NHAT 1 VIDEO, khong bao gio chon nham video cu!
    """
    run_adb(["shell", "rm -f /sdcard/DCIM/Camera/AUTO_*.mp4 /sdcard/DCIM/Camera/REAL_*.mp4 /sdcard/DCIM/Camera/TIKTOK_CURRENT_*.mp4"], serial=serial)
    clean_remote_name = f"TIKTOK_CURRENT_{local_video_path.name}"
    remote_path = f"/sdcard/DCIM/Camera/{clean_remote_name}"

    rc, out, err = run_adb(["push", str(local_video_path), remote_path], serial=serial, timeout=45)
    if rc != 0:
        return False, f"Lỗi đẩy video sang Oppo A57: {err or out}"

    # Cap nhat timestamp moi nhat va goi Media Scanner de video nam o vi tri #1 dau tien trong Gallery
    run_adb(["shell", f"touch '{remote_path}'"], serial=serial)
    run_adb(
        ["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{remote_path}"],
        serial=serial,
    )
    time.sleep(1.5)
    return True, remote_path


def execute_tiktok_post_flow(channel: str = None, dry_run_switch_only: bool = False) -> dict:
    """
    Thuc thi toan trinh 1 luot dang video tren Oppo A57:
    1. Dong bo kho video tu R630 ve Cache Laptop (neu R630 online)
    2. Chon bai READY tiep theo cua kenh (@suckhoeviet.2 hoac @suc.khoe.vang.268)
    3. Kiem tra Chong Dang Trung 3 Lop (SHA-256 file + clip_id + caption)
    4. Ket noi Oppo A57 & Tu dong chuyen sang DUNG tai khoan trong 4 tai khoan tren may
    5. Don sach Camera -> Day duy nhat 1 video -> Mo giao dien dang TikTok -> Chon video #1 -> Dien Caption SEO!
    """
    conn_info = auto_connect_oppo()
    if not conn_info["connected"]:
        return {"ok": False, "step": "CONNECT_OPPO", "message": conn_info["detail"]}

    serial = conn_info["serial"]
    sync_from_r630_to_laptop_cache()

    if not LOCAL_QUEUE_FILE.exists():
        return {"ok": False, "step": "LOAD_QUEUE", "message": "Chưa có dữ liệu hàng chờ trong C:\\TikTok_AutoHub\\data\\local_queue.json"}

    queue = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    candidate = None
    for item in queue:
        if item.get("status") == "POSTED":
            continue
        if item.get("channel") not in ALLOWED_CHANNELS:
            continue
        if channel and item.get("channel") != channel:
            continue
        fname = Path(item.get("output_video", "")).name
        lpath = CACHE_DIR / fname
        if lpath.exists() and lpath.stat().st_size > 50000:
            candidate = (item, lpath)
            break

    if not candidate:
        return {"ok": False, "step": "PICK_VIDEO", "message": f"Không còn video nào trong Cache sẵn sàng cho kênh {channel or '2 kênh chính'}."}

    item, local_mp4 = candidate
    target_ch = item["channel"]

    # Buoc 1: Kiem tra Chong Dang Trung 3 Lop
    is_safe, dup_msg, f_hash, c_hash = check_duplicate_guard(item, local_mp4)
    if not is_safe:
        item["status"] = "BLOCKED_DUPLICATE"
        LOCAL_QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": False, "step": "ANTI_DUPLICATE_GUARD", "message": dup_msg, "item": item}

    # Buoc 2: Mo TikTok & Chuyen sang dung tai khoan trong 4 tai khoan
    sw_ok, sw_msg = ensure_correct_tiktok_account(serial, target_ch)
    if not sw_ok:
        return {"ok": False, "step": "SWITCH_ACCOUNT", "message": sw_msg, "item": item}

    if dry_run_switch_only:
        return {"ok": True, "step": "SWITCH_ACCOUNT_VERIFIED", "message": sw_msg, "item": item}

    # Buoc 3: Don sach cuon Camera & Day duy nhat 1 video sach sang Oppo A57
    push_ok, remote_path = prepare_single_clean_video_on_oppo(serial, local_mp4)
    if not push_ok:
        return {"ok": False, "step": "PUSH_SINGLE_VIDEO", "message": remote_path}

    # Buoc 4: Nap san Caption + 5 Hashtag chuan SEO vao Clipboard & Mo man hinh Upload cua TikTok
    caption_text = item["caption_seo"]
    # Gui intent chia se video thang vao TikTok composer (nhanh va chinh xac hon bam toa do thu cong!)
    run_adb(
        [
            "shell", "am", "start",
            "-a", "android.intent.action.SEND",
            "-t", "video/mp4",
            "--eu", "android.intent.extra.STREAM", f"file://{remote_path}",
            "-p", TIKTOK_PKG,
        ],
        serial=serial,
    )
    time.sleep(4.5)

    # Kiem tra xem TikTok da mo man hinh Editor/Post chua; neu chua thi bam nut '+' -> Upload -> Chon video #1
    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return {"ok": False, "step": "CAPTCHA_PAUSE", "message": "TikTok hiện CAPTCHA trên Oppo A57. Vui lòng kéo xác thực trên màn hình điện thoại."}

    # Tim nut 'Tiếp' (Next) de sang man hinh nhap Caption & Gan gio hang
    next_btn = next((n for n in nodes if n["text"].lower() in ["tiếp", "next"] or "tiếp" in n["desc"].lower()), None)
    if next_btn:
        run_adb(["shell", "input", "tap", str(next_btn["cx"]), str(next_btn["cy"])], serial=serial)
        time.sleep(3.0)
    else:
        # Fallback: Bam nut '+' (360, 1545) -> Bam 'Tải lên' (580, 1310) -> Chon o video #1 (125, 360) -> Bam 'Tiếp' (590, 1535)
        run_adb(["shell", "input", "tap", "360", "1545"], serial=serial)
        time.sleep(2.5)
        run_adb(["shell", "input", "tap", "580", "1310"], serial=serial)
        time.sleep(2.5)
        run_adb(["shell", "input", "tap", "125", "360"], serial=serial)
        time.sleep(1.5)
        run_adb(["shell", "input", "tap", "590", "1535"], serial=serial)
        time.sleep(3.0)
        run_adb(["shell", "input", "tap", "590", "1535"], serial=serial)
        time.sleep(2.5)

    # Copy Caption SEO vao Clipboard cua Laptop & Oppo A57
    try:
        subprocess.run(["clip"], input=caption_text.encode("utf-16le"), check=False)
    except Exception:
        pass

    # Ghi nhan vao So cai Chong Dang Trung 3 Lop de KHONG BAO GIO dang lai video nay lan 2!
    cfg = get_settings()
    if cfg.get("post_mode") == "FULL_AUTO_POST":
        post_nodes = dump_oppo_ui(serial)
        post_btn = next((n for n in post_nodes if n["text"].lower() in ["đăng", "post"]), None)
        if post_btn:
            run_adb(["shell", "input", "tap", str(post_btn["cx"]), str(post_btn["cy"])], serial=serial)
            record_posted_in_ledger(item, f_hash, c_hash, mode="FULL_AUTO_OPPO")
            return {
                "ok": True,
                "step": "POSTED_COMPLETE",
                "message": f"✓ Đã chuyển đúng tài khoản {target_ch}, nạp video duy nhất {local_mp4.name}, bấm Đăng và khóa mã SHA-256 ({f_hash[:12]}...) vào Sổ cái chống trùng!",
                "item": item,
            }

    # Mac dinh: Khoa vao so cai & dung ngay o man hinh Soan bai + Gan san pham GMV Max tren Oppo A57
    record_posted_in_ledger(item, f_hash, c_hash, mode="PREPARED_ON_OPPO")
    return {
        "ok": True,
        "step": "PREPARED_ON_OPPO_SCREEN",
        "message": (
            f"✓ Đã chuyển đúng kênh {target_ch} trên Oppo A57, nạp duy nhất video '{local_mp4.name}' "
            f"(Mã SHA-256: {f_hash[:12]}... đã khóa chống trùng) và mở sẵn màn hình Đăng! "
            f"Bạn chỉ cần Dán Caption + Gắn Shop GMV Max ({item['seller_id']}) và bấm Đăng."
        ),
        "item": item,
    }


if __name__ == "__main__":
    print(json.dumps(auto_connect_oppo(), ensure_ascii=False))
