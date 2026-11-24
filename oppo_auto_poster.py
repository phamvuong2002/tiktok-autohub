# -*- coding: utf-8 -*-
"""
OPPO A57 SMART CONNECTOR, 4-ACCOUNT SWITCHER & 1-CLICK VIDEO + VIETNAMESE CAPTION SENDER
Theo dung luong nguoi dung yeu cau:
1. He thong TU DONG chuan bi Video da cat + Caption Tieng Viet CO DAU 100% + Len lich gian cach 1 Tieng / 1 Video.
2. Khi den gio nhac (moi 60 phut) hoac khi bam nut 'Day Video Sang Oppo A57':
   - Kiem tra Chong Dang Trung 3 Lop (SHA-256 file + clip_id + caption)
   - Tu dong chuyen TikTok tren Oppo A57 ve dung tai khoan (@suckhoeviet.2 hoac @suc.khoe.vang.268)
   - Xoa sach video cu trong Camera va day DUY NHAT 1 video cua khung gio do vao dau cuon Camera Oppo A57
   - Mo san the Copy Caption Tieng Viet CO DAU 100% ngay tren man hinh Oppo A57 de nguoi dung chi can cham Copy -> Dan vao TikTok -> Gan gio hang & Dang!
3. Nguoi dung tu lam buoc cuoi va bam 'Danh Dau Da Dang' -> Khoa cung SHA-256 vao So cai Chong Trung & Dem nguoc 60 phut cho bai tiep theo!
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
TIKTOK_SPLASH = "com.ss.android.ugc.trill/com.ss.android.ugc.aweme.splash.SplashActivity"


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


def get_laptop_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_laptop_subnet_prefix() -> str:
    ip = get_laptop_lan_ip()
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}.{parts[2]}" if len(parts) == 4 else "192.168.1"


def quick_check_oppo_connected() -> dict:
    """Kiem tra tuc thi (<50ms) xem Oppo A57 da ket noi trong danh sach adb devices chua."""
    _, out, _ = run_adb(["devices", "-l"], timeout=3)
    lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip() and "\toffline" not in ln]
    for ln in lines:
        if "device " in ln:
            serial = ln.split()[0]
            if "_adb-tls-connect" in serial:
                mode = "WIFI_MDNS_AUTO"
            elif ":" in serial:
                mode = "WIFI_IP"
            else:
                mode = "USB"
            return {"connected": True, "serial": serial, "mode": mode, "detail": ln}
    return {
        "connected": False,
        "serial": None,
        "mode": "NONE",
        "detail": "Chưa kết nối Oppo A57. Hãy bật Gỡ lỗi không dây trên Oppo A57 (hoặc cắm cáp USB 1 lần) rồi bấm 'Tự Động Tìm & Nối Oppo A57'.",
    }


def auto_connect_oppo(hint_ip: str = None) -> dict:
    _, out, _ = run_adb(["devices", "-l"])
    lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip() and "\toffline" not in ln]

    if "\toffline" in out and not lines:
        run_adb(["disconnect"])
        _, out, _ = run_adb(["devices", "-l"])
        lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]

    for ln in lines:
        if "device " in ln:
            serial = ln.split()[0]
            is_physical_usb = (":" not in serial) and ("_adb-tls-connect" not in serial)
            if is_physical_usb:
                run_adb(["tcpip", "5555"], serial=serial)
                mode = "USB"
            elif "_adb-tls-connect" in serial:
                mode = "WIFI_MDNS_AUTO"
            else:
                mode = "WIFI_IP"
            return {"connected": True, "serial": serial, "mode": mode, "detail": ln}

    cfg = get_settings()
    target_ip = (hint_ip or cfg.get("oppo_last_ip") or "192.168.1.95").split(":")[0]

    if hint_ip and ":" in hint_ip:
        _, co, _ = run_adb(["connect", hint_ip])
        if "connected to" in co.lower():
            cfg["oppo_last_ip"] = hint_ip.split(":")[0]
            (DATA_DIR / "hub_settings.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"connected": True, "serial": hint_ip, "mode": "WIFI_IP", "detail": co}

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
            if f"{addr}\tdevice" in dout or (f"{addr} " in dout and "offline" not in dout):
                return {"connected": True, "serial": addr, "mode": "WIFI_AUTO", "detail": f"Tự động nối {addr}"}

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
        "detail": f"Chưa thấy Oppo A57 mở cổng trên {target_ip} (hoặc mạng {subnet}.x). Hãy bật Gỡ lỗi không dây trên Oppo A57 hoặc cắm cáp USB vào Laptop.",
    }


def pair_oppo_wireless(pair_ip_port: str, pair_code: str) -> dict:
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
    xml_local = DATA_DIR / "window_dump.xml"
    try:
        if xml_local.exists():
            xml_local.unlink()
    except Exception:
        pass
    run_adb(
        ["shell", "rm -f /sdcard/window_dump.xml && uiautomator dump --compressed /sdcard/window_dump.xml"],
        serial=serial,
        timeout=12,
    )
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
    clean_handle = target_handle.lstrip("@").lower()
    run_adb(["shell", "input", "keyevent", "224"], serial=serial)
    run_adb(["shell", "cmd", "statusbar", "collapse"], serial=serial)
    time.sleep(0.5)

    run_adb(["shell", "am", "start", "-n", TIKTOK_SPLASH], serial=serial)
    time.sleep(3.0)

    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return False, "TẠM DỪNG AN TOÀN: Màn hình TikTok đang hiện CAPTCHA. Bạn vui lòng kéo xác thực trên điện thoại."

    for _ in range(3):
        if any(n["id"].endswith(":id/oxl") or n["text"] == "Hồ sơ" or n["desc"] == "Hồ sơ" for n in nodes):
            break
        run_adb(["shell", "input", "keyevent", "4"], serial=serial)
        time.sleep(1.2)
        nodes = dump_oppo_ui(serial)

    prof_tab = next((n for n in nodes if n["id"].endswith(":id/oxl") or n["desc"] == "Hồ sơ"), None)
    if prof_tab and prof_tab["cx"] > 0:
        run_adb(["shell", "input", "tap", str(prof_tab["cx"]), str(prof_tab["cy"])], serial=serial)
    else:
        run_adb(["shell", "input", "tap", "648", "1563"], serial=serial)
    time.sleep(2.2)

    nodes = dump_oppo_ui(serial)
    screen_text = " ".join((n["text"] + " " + n["desc"]).lower() for n in nodes)
    if f"@{clean_handle}" in screen_text or clean_handle in screen_text:
        return True, f"✓ Đã xác nhận Oppo A57 đang ở đúng tài khoản @{clean_handle}"

    switcher_btn = next((n for n in nodes if n["id"].endswith(":id/tjz") and n["cx"] > 0), None)
    if switcher_btn:
        run_adb(["shell", "input", "tap", str(switcher_btn["cx"]), str(switcher_btn["cy"])], serial=serial)
    else:
        run_adb(["shell", "input", "tap", "250", "231"], serial=serial)
    time.sleep(2.2)

    sheet_nodes = dump_oppo_ui(serial)
    target_node = None
    for n in sheet_nodes:
        combined = (n["text"] + " " + n["desc"]).lower()
        if clean_handle in combined and n["cy"] > 820:
            target_node = n
            break

    if not target_node:
        return False, f"Không tìm thấy tài khoản '@{clean_handle}' trong bảng chuyển đổi 4 tài khoản trên Oppo A57."

    run_adb(["shell", "input", "tap", str(target_node["cx"]), str(target_node["cy"])], serial=serial)
    time.sleep(3.5)
    return True, f"✓ Đã tự động chuyển sang đúng tài khoản @{clean_handle} trên Oppo A57!"


def prepare_single_clean_video_on_oppo(serial: str, local_video_path: Path) -> tuple[bool, str]:
    """
    Xoa TOAN BO cac file video AUTO_*/REAL_*/TIKTOK_CURRENT_* cu trong /sdcard/DCIM/Camera/ va /sdcard/Download/,
    sau do day DUY NHAT 1 file video cua luot dang nay vao Camera va quet Media Scanner
    -> Dam bao o vi tri #1 dau tien trong Gallery CHI CO DUY NHAT VIDEO HIEN TAI!
    """
    run_adb(
        [
            "shell",
            "rm -f /sdcard/DCIM/Camera/AUTO_*.mp4 /sdcard/DCIM/Camera/REAL_*.mp4 /sdcard/DCIM/Camera/TIKTOK_CURRENT_*.mp4 "
            "/sdcard/Download/AUTO_*.mp4 /sdcard/Download/REAL_*.mp4",
        ],
        serial=serial,
    )
    clean_remote_name = f"TIKTOK_CURRENT_{local_video_path.name}"
    remote_path = f"/sdcard/DCIM/Camera/{clean_remote_name}"

    rc, out, err = run_adb(["push", str(local_video_path), remote_path], serial=serial, timeout=45)
    if rc != 0:
        return False, f"Lỗi đẩy video sang Oppo A57: {err or out}"

    run_adb(["shell", f"touch '{remote_path}'"], serial=serial)
    run_adb(
        ["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{remote_path}"],
        serial=serial,
    )
    time.sleep(1.5)
    return True, remote_path


def send_video_and_vietnamese_card_to_oppo(item_id: str = None, channel: str = None, switch_account: bool = True) -> dict:
    """
    LUONG BAN TU DONG CHUAN THEO YEU CAU CUA NGUOI DUNG:
    - Kiem tra Chong Dang Trung 3 Lop (SHA-256)
    - Copy Caption Tieng Viet CO DAU 100% vao Clipboard Laptop
    - Neu Oppo A57 dang ket noi:
      + Xoa video cu trong Camera & Day DUY NHAT 1 video (.mp4) cua bai nay vao dau cuon Camera Oppo A57
      + Chuyen TikTok tren Oppo A57 sang dung tai khoan (@suckhoeviet.2 hoac @suc.khoe.vang.268)
      + Mo the Mobile Helper (http://<IP-Laptop>:8099/mobile?id=<item_id>) tren Oppo A57 de nguoi dung cham 1 nut
        la Copy Caption Tieng Viet CO DAU 100% vao Clipboard dien thoai -> Tu dan va dang!
    - KHONG tu y danh dau POSTED cho den khi nguoi dung bam nut '[✅ Đánh Dấu Đã Đăng]'!
    """
    sync_from_r630_to_laptop_cache()
    if not LOCAL_QUEUE_FILE.exists():
        return {"ok": False, "message": "Chưa có dữ liệu hàng chờ trong local_queue.json"}

    queue = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    candidate = None
    for item in queue:
        if item.get("status") == "POSTED":
            continue
        if item.get("channel") not in ALLOWED_CHANNELS:
            continue
        if item_id and item.get("id") != item_id:
            continue
        if channel and item.get("channel") != channel:
            continue
        fname = Path(item.get("output_video", "")).name
        lpath = CACHE_DIR / fname
        if lpath.exists() and lpath.stat().st_size > 50000:
            candidate = (item, lpath)
            break

    if not candidate:
        return {"ok": False, "message": "Không tìm thấy video sẵn sàng trong kho Cache."}

    item, local_mp4 = candidate
    target_ch = item["channel"]

    # 1. Kiem tra Chong Dang Trung 3 Lop
    is_safe, dup_msg, f_hash, c_hash = check_duplicate_guard(item, local_mp4)
    if not is_safe:
        return {"ok": False, "step": "ANTI_DUPLICATE_GUARD", "message": dup_msg, "item": item}

    # 2. Copy Caption Tieng Viet CO DAU 100% vao Clipboard cua Laptop
    caption_vn = item["caption_seo"]
    try:
        subprocess.run(["clip"], input=caption_vn.encode("utf-16le"), check=False)
    except Exception:
        pass

    # 3. Neu Oppo A57 dang ket noi: Day duy nhat 1 video sang Camera + Mo the Copy Caption Tieng Viet Co Dau tren Oppo A57
    conn_info = auto_connect_oppo()
    if not conn_info["connected"]:
        return {
            "ok": True,
            "oppo_pushed": False,
            "message": (
                f"📋 Đã Copy Caption Tiếng Việt có dấu của kênh {target_ch} vào Clipboard Laptop! "
                f"(Oppo A57 hiện chưa nối ADB; bạn có thể mở http://{get_laptop_lan_ip()}:8099/mobile trên trình duyệt Oppo A57 để tải video & copy caption tiếng Việt 1 chạm)."
            ),
            "item": item,
        }

    serial = conn_info["serial"]
    push_ok, remote_path = prepare_single_clean_video_on_oppo(serial, local_mp4)
    if not push_ok:
        return {"ok": False, "message": remote_path}

    sw_msg = ""
    if switch_account:
        _, sw_msg = ensure_correct_tiktok_account(serial, target_ch)

    # Mo trang Mobile Helper (1-Tap Copy Caption Tieng Viet Co Dau & Mo TikTok) ngay tren Oppo A57!
    lan_ip = get_laptop_lan_ip()
    mobile_url = f"http://{lan_ip}:8099/mobile?id={item['id']}"
    run_adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", mobile_url], serial=serial)

    return {
        "ok": True,
        "oppo_pushed": True,
        "message": (
            f"📲 Đã đẩy DUY NHAT video '{local_mp4.name}' vào đầu cuộn Camera Oppo A57, {sw_msg} "
            f"và mở sẵn thẻ Copy Caption Tiếng Việt CÓ DẤU trên màn hình Oppo A57! "
            f"Sau khi bạn tự đăng xong trên điện thoại, hãy bấm nút [✅ Đánh Dấu Đã Đăng] để hệ thống khóa chống trùng & đếm ngược 1 tiếng tiếp theo."
        ),
        "item": item,
    }


def mark_video_as_posted(item_id: str) -> dict:
    """
    Khi nguoi dung tu dang xong tren Oppo A57 va bam '[✅ Đánh Dấu Đã Đăng]':
    - Tinh ma bam SHA-256 cua file video & caption
    - Khoa cung vao So cai Chong Dang Trung 3 Lop (anti_duplicate_ledger.db)
    - Danh dau status = POSTED trong hang cho
    """
    if not LOCAL_QUEUE_FILE.exists():
        return {"ok": False, "message": "Không tìm thấy local_queue.json"}

    queue = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    target_item = next((x for x in queue if x.get("id") == item_id), None)
    if not target_item:
        return {"ok": False, "message": f"Không tìm thấy bài có mã {item_id}"}

    fname = Path(target_item.get("output_video", "")).name
    local_mp4 = CACHE_DIR / fname
    is_safe, dup_msg, f_hash, c_hash = check_duplicate_guard(target_item, local_mp4)
    if not is_safe:
        return {"ok": False, "message": dup_msg}

    record_posted_in_ledger(target_item, f_hash, c_hash, mode="USER_CONFIRMED_POSTED")
    return {
        "ok": True,
        "message": (
            f"✅ Đã đánh dấu ĐÃ ĐĂNG cho video '{fname}' trên kênh {target_item['channel']}! "
            f"Đã khóa mã SHA-256 ({f_hash[:14]}...) vào Sổ cái chống trùng và bắt đầu đếm ngược 60 phút (1 tiếng) để nhắc bài tiếp theo."
        ),
        "item": target_item,
        "file_sha256": f_hash,
    }
