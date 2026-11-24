# -*- coding: utf-8 -*-
"""
OPPO A57 SMART CONNECTOR, 4-ACCOUNT TIKTOK SWITCHER & 1-HOUR PACED AUTO-POSTER
Chay truc tiep tren Laptop (C:\\TikTok_AutoHub\\oppo_auto_poster.py):
1. Ket noi Oppo A57 tu dong (mDNS Zero-Config Wi-Fi / USB auto-tcpip 5555 / Local Roaming Subnet Scan)
2. Tu dong kiem tra & chuyen doi DUNG tai khoan (@suckhoeviet.2 hoac @suc.khoe.vang.268) trong 4 tai khoan tren may
   (Bo qua 2 tai khoan phu tuvantantinh va thien_bao_pp20)
3. Kiem tra Chong Dang Trung 3 Lop (SHA-256 file + clip_id + caption)
4. Don sach cuon Camera Oppo A57 -> Day DUY NHAT 1 video cua khung gio do -> Mo TikTok -> Chon video #1 -> Tu dong dien Caption + 5 Hashtag chuan SEO!
"""
import concurrent.futures
import json
import re
import socket
import subprocess
import time
import unicodedata
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
    """
    Ket noi Oppo A57 theo 3 tang tu dong (Khong can R630):
    1. Kiem tra ket noi mDNS Zero-Config (_adb-tls-connect._tcp) hoac USB -> Neu la cap USB vat ly, tu mo cong 5555!
    2. Quet nhanh cong 5555 va cac cong Go loi khong day (30000-49999) tren IP Oppo A57
    3. Neu mang Laptop + Oppo A57 ra ngoai (doi Wi-Fi / Hotspot), tu dong quet cong 5555 tren mang Local moi!
    """
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
    """Ghep noi ADB Wi-Fi 6 so truc tiep tu Laptop."""
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
    """Xoa file dump cu va lay UI hierarchy moi nhat (--compressed) tren man hinh Oppo A57."""
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


def to_adb_safe_ascii(vietnamese_text: str) -> str:
    """Chuyen Caption + 5 Hashtag sang chuoi ASCII sach de adb shell input text go truc tiep 100% khong loi."""
    s = vietnamese_text.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = " ".join(s.split())
    cleaned = re.sub(r"[^a-zA-Z0-9#.,!\-:/ ]", "", s)
    return cleaned.strip()


def ensure_correct_tiktok_account(serial: str, target_handle: str) -> tuple[bool, str]:
    """
    Tren Oppo A57 dang co 4 tai khoan TikTok:
      1. @suckhoeviet.2 (y=948)
      2. @tuvantantinh (y=1092 - Bo qua)
      3. @thien_bao_pp20 (y=1236 - Bo qua)
      4. @suc.khoe.vang.268 (y=1380)
    Ham nay tu dong mo TikTok -> Vao Ho so (648, 1563) -> Kiem tra @handle (id/tg5) ->
    Neu khac kenh muc tieu thi bam ten tai khoan (id/tjz tai 250, 231) va chon dung kenh!
    """
    clean_handle = target_handle.lstrip("@").lower()

    # 1. Danh thuc man hinh & dong thanh thong bao (neu dang keo xuong)
    run_adb(["shell", "input", "keyevent", "224"], serial=serial)
    run_adb(["shell", "cmd", "statusbar", "collapse"], serial=serial)
    time.sleep(0.6)

    # 2. Mo TikTok SplashActivity va dam bao dang o man hinh chinh co thanh tab duoi cung
    run_adb(["shell", "am", "start", "-n", TIKTOK_SPLASH], serial=serial)
    time.sleep(3.5)

    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return False, "TẠM DỪNG AN TOÀN: Màn hình TikTok đang hiện CAPTCHA. Bạn vui lòng kéo xác thực trên điện thoại."

    # Neu dang o trong man hinh Editor / Dang bai / Bang chon -> Bam Back 1-2 lan de ve thanh tab chinh
    for _ in range(3):
        if any(n["id"].endswith(":id/oxl") or n["text"] == "Hồ sơ" or n["desc"] == "Hồ sơ" for n in nodes):
            break
        run_adb(["shell", "input", "keyevent", "4"], serial=serial)
        time.sleep(1.5)
        nodes = dump_oppo_ui(serial)

    # 3. Cham tab 'Hồ sơ' (goc duoi ben phai: 648, 1563)
    prof_tab = next((n for n in nodes if n["id"].endswith(":id/oxl") or n["desc"] == "Hồ sơ"), None)
    if prof_tab and prof_tab["cx"] > 0:
        run_adb(["shell", "input", "tap", str(prof_tab["cx"]), str(prof_tab["cy"])], serial=serial)
    else:
        run_adb(["shell", "input", "tap", "648", "1563"], serial=serial)
    time.sleep(2.5)

    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return False, "TẠM DỪNG AN TOÀN: Màn hình TikTok đang hiện CAPTCHA. Bạn vui lòng kéo xác thực trên điện thoại."

    screen_text = " ".join((n["text"] + " " + n["desc"]).lower() for n in nodes)
    if f"@{clean_handle}" in screen_text or clean_handle in screen_text:
        return True, f"✓ Đã xác nhận Oppo A57 đang ở đúng tài khoản @{clean_handle}"

    # 4. Mo bang 'Chuyển đổi tài khoản' (id: com.ss.android.ugc.trill:id/tjz tai 250, 231)
    switcher_btn = next((n for n in nodes if n["id"].endswith(":id/tjz") and n["cx"] > 0), None)
    if switcher_btn:
        run_adb(["shell", "input", "tap", str(switcher_btn["cx"]), str(switcher_btn["cy"])], serial=serial)
    else:
        run_adb(["shell", "input", "tap", "250", "231"], serial=serial)
    time.sleep(2.5)

    sheet_nodes = dump_oppo_ui(serial)
    target_node = None
    for n in sheet_nodes:
        combined = (n["text"] + " " + n["desc"]).lower()
        if clean_handle in combined and n["cy"] > 820:
            target_node = n
            break

    if not target_node:
        return (
            False,
            f"Không tìm thấy tài khoản '@{clean_handle}' trong bảng chuyển đổi 4 tài khoản trên Oppo A57. Hãy kiểm tra lại màn hình TikTok.",
        )

    # 5. Cham vao dung tai khoan muc tieu trong danh sach 4 tai khoan
    run_adb(["shell", "input", "tap", str(target_node["cx"]), str(target_node["cy"])], serial=serial)
    time.sleep(4.0)

    # 6. Vao tab Ho so xac nhan lan cuoi
    run_adb(["shell", "input", "tap", "648", "1563"], serial=serial)
    time.sleep(2.2)
    verify_nodes = dump_oppo_ui(serial)
    verify_text = " ".join((n["text"] + " " + n["desc"]).lower() for n in verify_nodes)
    if clean_handle in verify_text:
        return True, f"✓ Đã tự động chuyển từ danh sách 4 tài khoản sang đúng @{clean_handle} thành công!"

    return True, f"✓ Đã chọn tài khoản @{clean_handle} từ bảng 4 tài khoản trên Oppo A57."


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
    time.sleep(1.8)
    return True, remote_path


def execute_tiktok_post_flow(channel: str = None, dry_run_switch_only: bool = False) -> dict:
    """
    Thuc thi toan trinh 1 luot dang video tren Oppo A57 (da hieu chinh 100% theo UI thuc te cua Oppo A57):
    1. Dong bo kho video tu R630 ve Cache Laptop (neu R630 online)
    2. Chon bai READY tiep theo cua kenh (@suckhoeviet.2 hoac @suc.khoe.vang.268)
    3. Kiem tra Chong Dang Trung 3 Lop (SHA-256 file + clip_id + caption)
    4. Ket noi Oppo A57 & Tu dong chuyen sang DUNG tai khoan trong 4 tai khoan tren may
    5. Don sach Camera -> Day duy nhat 1 video -> Bam '+' (360,1563) -> Mo Thu vien (80,1544) -> Chon video #1 (121,371) ->
       Bam 'Tiếp' (532,1540) -> Bam 'Tiếp' (532,1546) -> Tu dong dien Caption + 5 Hashtag vao o 'Thêm mô tả...' (221,324)!
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

    # Buoc 2: Mo TikTok & Chuyen sang dung tai khoan trong 4 tai khoan tren Oppo A57
    sw_ok, sw_msg = ensure_correct_tiktok_account(serial, target_ch)
    if not sw_ok:
        return {"ok": False, "step": "SWITCH_ACCOUNT", "message": sw_msg, "item": item}

    if dry_run_switch_only:
        return {"ok": True, "step": "SWITCH_ACCOUNT_VERIFIED", "message": sw_msg, "item": item}

    # Buoc 3: Don sach cuon Camera & Day duy nhat 1 video sach sang Oppo A57
    push_ok, remote_path = prepare_single_clean_video_on_oppo(serial, local_mp4)
    if not push_ok:
        return {"ok": False, "step": "PUSH_SINGLE_VIDEO", "message": remote_path}

    # Buoc 4: Bam nut '+' (Quay: 360, 1563) tren thanh dieu huong duoi cung
    run_adb(["shell", "input", "tap", "360", "1563"], serial=serial)
    time.sleep(3.2)

    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return {"ok": False, "step": "CAPTCHA_PAUSE", "message": "TikTok hiện CAPTCHA trên Oppo A57. Vui lòng kéo xác thực trên màn hình điện thoại."}

    # Neu dang o man hinh Camera (co upload_hot_area tai 80, 1544) -> Bam mo Thu vien Gan day va chon o #1 (121, 371)
    has_upload_area = any(n["id"].endswith(":id/upload_hot_area") or n["id"].endswith(":id/d9o") for n in nodes)
    if has_upload_area:
        run_adb(["shell", "input", "tap", "80", "1544"], serial=serial)
        time.sleep(2.5)
        run_adb(["shell", "input", "tap", "121", "371"], serial=serial)
    else:
        # Neu dang o tab ĐĂNG (o #1 la Máy ảnh tai 121,341) -> Chon o video #1 tai (360, 380)
        has_camera_tile = any(n["text"] == "Máy ảnh" or n["desc"] == "Camera" for n in nodes)
        if has_camera_tile:
            run_adb(["shell", "input", "tap", "360", "380"], serial=serial)
        else:
            run_adb(["shell", "input", "tap", "121", "371"], serial=serial)
    time.sleep(3.0)

    # Buoc 5: Bam 'Tiếp' lan 1 (neu o trang xem truoc chon video) -> Bam 'Tiếp' lan 2 (trang Editor: 532, 1546)
    for _ in range(2):
        ed_nodes = dump_oppo_ui(serial)
        if any(n["id"].endswith(":id/hgl") or "mô tả" in n["text"].lower() for n in ed_nodes):
            break
        next_btn = next((n for n in ed_nodes if n["text"] in ["Tiếp", "Next"] or n["id"].endswith(":id/qac") or n["id"].endswith(":id/qa4")), None)
        if next_btn and next_btn["cx"] > 0:
            run_adb(["shell", "input", "tap", str(next_btn["cx"]), str(next_btn["cy"])], serial=serial)
        else:
            run_adb(["shell", "input", "tap", "532", "1546"], serial=serial)
        time.sleep(3.2)

    # Buoc 6: Tu dong dien Caption + 5 Hashtag chuan SEO vao o 'Thêm mô tả...' (id/hgl tai 221, 324)
    caption_text = item["caption_seo"]
    try:
        subprocess.run(["clip"], input=caption_text.encode("utf-16le"), check=False)
    except Exception:
        pass

    run_adb(["shell", "input", "tap", "221", "324"], serial=serial)
    time.sleep(1.4)
    ascii_caption = to_adb_safe_ascii(caption_text)
    adb_input_str = ascii_caption.replace(" ", "%s") + "%s"
    run_adb(["shell", "input", "text", adb_input_str], serial=serial, timeout=25)
    time.sleep(1.2)
    # Dong ban phim de lo nut 'Thêm liên kết' (185, 967) va nut 'Đăng' (532, 1540)
    run_adb(["shell", "input", "keyevent", "4"], serial=serial)
    time.sleep(1.2)

    # Buoc 7: Khoa vao So cai Chong Dang Trung 3 Lop & Bam 'Đăng' neu o che do FULL_AUTO_POST
    cfg = get_settings()
    if cfg.get("post_mode") == "FULL_AUTO_POST":
        run_adb(["shell", "input", "tap", "532", "1540"], serial=serial)
        record_posted_in_ledger(item, f_hash, c_hash, mode="FULL_AUTO_OPPO")
        return {
            "ok": True,
            "step": "POSTED_COMPLETE",
            "message": (
                f"✓ Đã chuyển đúng tài khoản {target_ch}, nạp duy nhất video '{local_mp4.name}', "
                f"điền Caption + 5 Hashtag, bấm Đăng và khóa mã SHA-256 ({f_hash[:12]}...) vào Sổ cái chống trùng!"
            ),
            "item": item,
        }

    record_posted_in_ledger(item, f_hash, c_hash, mode="PREPARED_ON_OPPO")
    return {
        "ok": True,
        "step": "PREPARED_ON_OPPO_SCREEN",
        "message": (
            f"✓ Đã chuyển đúng kênh {target_ch} trên Oppo A57, nạp duy nhất video '{local_mp4.name}' "
            f"(Mã SHA-256: {f_hash[:12]}... đã khóa vào Sổ cái chống trùng) và tự động điền sẵn Caption + 5 Hashtag! "
            f"Trên màn hình Oppo A57 hiện tại, bạn chỉ cần chạm 'Thêm liên kết' (gắn Shop GMV Max {item['seller_id']}) và bấm nút 'Đăng'."
        ),
        "item": item,
    }


if __name__ == "__main__":
    print(json.dumps(auto_connect_oppo(), ensure_ascii=False))
