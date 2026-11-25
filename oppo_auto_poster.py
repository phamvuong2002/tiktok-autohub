# -*- coding: utf-8 -*-
"""
OPPO A57 SMART ROAMING CONNECTOR, 4-ACCOUNT SWITCHER & AUTO-SAVE-DRAFT (LƯU NHÁP) ENGINE
Hoan thien theo dung yeu cau cua nguoi dung khi mang Laptop + Oppo A57 ra ngoai (khac mang R630):
1. Ket noi Oppo A57 tren mang LAN moi (vd 10.110.8.x):
   - Neu cam cap USB 3 giay: Tu dong bat cong 5555, doc luon IP Wi-Fi moi cua Oppo A57 va tu ket noi ADB Wi-Fi (rut cap dung ngay).
   - Neu nhap IP hoac IP:Port (hoac mo trang /mobile tren Oppo A57): Tu dong quet cong Go loi khong day (5555 & 30000-49999), ket noi khong can ma 6 so (do da dong bo khoa RSA) va tu khoa luon cong 5555!
2. Luong TU DONG LUU NHAP (Auto-Save-Draft) kem CAPTION TIENG VIET CO DAU 100%:
   - Kiem tra Chong Dang Trung 3 Lop (SHA-256 file + clip_id + caption)
   - Nap Caption Tieng Viet CO DAU 100% vao Clipboard Oppo A57 (qua trang /auto_copy + input tap + KEYCODE_PASTE 279, khong can cai APK cu!)
   - Tu dong chuyen TikTok tren Oppo A57 ve dung tai khoan (@suckhoeviet.2 hoac @suc.khoe.vang.268)
   - Xoa video cu trong Camera -> Day DUY NHAT 1 video cua khung gio do -> Mo TikTok '+' -> Chon video #1 -> 'Tiếp' -> 'Tiếp'
   - Dan Caption Tieng Viet CO DAU 100% + 5 Hashtag vao o 'Thêm mô tả...' (221, 324)
   - Tu dong bam nut 'Nháp' (com.ss.android.ugc.trill:id/gqm tai 188, 1540) de LUU NHAP!
3. Nguoi dung chi can mo muc Nhap khi den gio nhac (moi 1 tieng), chon san pham GMV Max va bam Dang!
"""
import concurrent.futures
import json
import re
import socket
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from anti_dup_sync import (
    ALLOWED_CHANNELS,
    CACHE_DIR,
    DATA_DIR,
    HUB_DIR,
    LOCAL_QUEUE_FILE,
    SETTINGS_FILE,
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


def get_laptop_default_gateway() -> str:
    """Lay IP Default Gateway cua Wi-Fi Laptop (Khi Laptop bat Hotspot 'OPPO A57', Default Gateway CHINH LA IP cua Oppo A57!)."""
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=4).stdout
        # Tim Default Gateway cua Wireless LAN adapter Wi-Fi
        wifi_part = out.split("Wireless LAN adapter Wi-Fi:")[-1] if "Wireless LAN adapter Wi-Fi:" in out else out
        m = re.search(r"Default Gateway[\s\.]+:\s*(\d+\.\d+\.\d+\.\d+)", wifi_part)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def try_auto_join_oppo_a57_hotspot() -> tuple[bool, str]:
    """
    Kiem tra xem tren Oppo A57 da bat 'Diem phat song ca nhan' (SSID: 'OPPO A57') chua.
    Neu thay song 'OPPO A57', Laptop tu dong chuyen sang bat Wi-Fi 'OPPO A57' (da luu san mat khau vuong2002)
    de vuot qua hoan toan AP Isolation cua Wi-Fi truong DHQG-HCM!
    """
    try:
        iface = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=4).stdout
        if "OPPO A57" in iface:
            gw = get_laptop_default_gateway()
            return True, gw

        nets = subprocess.run(["netsh", "wlan", "show", "networks"], capture_output=True, text=True, timeout=4).stdout
        if "OPPO A57" in nets:
            subprocess.run(["netsh", "wlan", "connect", "name=OPPO A57"], capture_output=True, text=True, timeout=5)
            time.sleep(4.0)
            run_adb(["kill-server"])
            time.sleep(0.5)
            run_adb(["start-server"])
            time.sleep(1.5)
            gw = get_laptop_default_gateway()
            return True, gw
    except Exception:
        pass
    return False, ""


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
                mode = "WIFI_LAN"
            else:
                mode = "USB"
            return {"connected": True, "serial": serial, "mode": mode, "detail": ln}
    return {
        "connected": False,
        "serial": None,
        "mode": "NONE",
        "detail": (
            "Do Wi-Fi trường ĐHQG-HCM (10.110.8.x) chặn kết nối giữa các máy và chặn phát lại Hotspot từ Laptop, "
            "bạn chỉ cần bật 'Điểm phát sóng cá nhân' (OPPO A57) trên điện thoại (hoặc cắm cáp USB) rồi bấm nút vàng 'Tự Động Tìm & Nối Oppo A57': "
            "Laptop sẽ TỰ ĐỘNG bắt vào sóng 'OPPO A57' và kết nối ngay!"
        ),
    }


def scan_and_connect_single_ip(target_ip: str) -> dict:
    """Quet cong 5555 va 30000..49999 tren 1 IP Oppo A57 xac dinh va tu khoa cong 5555."""
    target_ip = target_ip.strip().split(":")[0]
    if not target_ip or target_ip == "127.0.0.1":
        return {"connected": False}

    def probe_port(p: int):
        try:
            s = socket.create_connection((target_ip, p), 0.25)
            s.close()
            return p
        except Exception:
            return None

    open_ports = []
    if probe_port(5555):
        open_ports.append(5555)
    else:
        with concurrent.futures.ThreadPoolExecutor(80) as ex:
            open_ports = [p for p in ex.map(probe_port, range(30000, 49999)) if p]

    for p in open_ports:
        addr = f"{target_ip}:{p}"
        _, co, _ = run_adb(["connect", addr])
        if "connected to" in co.lower() or "already connected" in co.lower():
            time.sleep(0.5)
            _, dout, _ = run_adb(["devices", "-l"])
            if f"{addr}\tdevice" in dout or (f"{addr} " in dout and "offline" not in dout):
                cfg = get_settings()
                cfg["oppo_last_ip"] = target_ip
                SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                if p != 5555:
                    run_adb(["tcpip", "5555"], serial=addr)
                    time.sleep(1.0)
                    run_adb(["connect", f"{target_ip}:5555"])
                return {"connected": True, "serial": addr, "mode": "WIFI_LAN_AUTO", "detail": f"✓ Đã kết nối Oppo A57 thành công tại {addr}"}
    return {"connected": False, "detail": f"Không tìm thấy cổng Gỡ lỗi không dây mở trên IP {target_ip}. Hãy kiểm tra màn hình Gỡ lỗi không dây trên Oppo A57."}


def auto_connect_oppo(hint_ip: str = None) -> dict:
    """
    Ket noi Oppo A57 thong minh khi mang Laptop + Oppo A57 ra ngoai (khac mang R630):
    1. Kiem tra ket noi hien co (USB / mDNS / Wi-Fi). Neu la cap USB vat ly:
       -> Tu dong bat cong 5555 + Doc IP wlan0 cua Oppo A57 + Tu ket noi Wi-Fi luon!
    2. Neu nguoi dung nhap IP:Port hoac IP (tu man hinh Go loi khong day) -> Ket noi thang khong can ma 6 so!
    3. Quet nhanh IP Oppo A57 da luu va dai mang Local hien tai.
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
            # Mo duong ham ADB Reverse (tcp:8099 -> tcp:8099) de http://127.0.0.1:8099 chay truc tiep tren Oppo A57 qua cap USB/ADB!
            run_adb(["reverse", "tcp:8099", "tcp:8099"], serial=serial)
            if is_physical_usb:
                return {
                    "connected": True,
                    "serial": serial,
                    "mode": "USB_DIRECT",
                    "detail": f"✓ Đã kết nối trực tiếp Oppo A57 qua cáp USB ({serial})",
                }
            elif "_adb-tls-connect" in serial:
                return {"connected": True, "serial": serial, "mode": "WIFI_MDNS_AUTO", "detail": ln}
            else:
                return {"connected": True, "serial": serial, "mode": "WIFI_LAN", "detail": ln}

    # Neu nguoi dung nhap IP:Port hoac IP
    if hint_ip:
        hint_ip = hint_ip.strip()
        if ":" in hint_ip:
            _, co, _ = run_adb(["connect", hint_ip])
            if "connected to" in co.lower() or "already connected" in co.lower():
                ip_only = hint_ip.split(":")[0]
                cfg = get_settings()
                cfg["oppo_last_ip"] = ip_only
                SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"connected": True, "serial": hint_ip, "mode": "WIFI_DIRECT", "detail": f"Đã kết nối {hint_ip}"}
        else:
            res = scan_and_connect_single_ip(hint_ip)
            if res.get("connected"):
                return res

    # Thu tu dong chuyen Laptop sang bat Hotspot 'OPPO A57' cua dien thoai (neu nguoi dung da bat Diem phat song ca nhan tren Oppo A57)
    joined_oppo_hs, gw_ip = try_auto_join_oppo_a57_hotspot()

    # Thu lam moi mDNS tren giao dien mang moi
    _, mdns_out, _ = run_adb(["mdns", "services"])
    if "_adb-tls-connect" in mdns_out:
        time.sleep(0.5)
        q = quick_check_oppo_connected()
        if q["connected"]:
            return q

    # Neu Laptop dang ket noi vao Hotspot 'OPPO A57', Default Gateway (gw_ip) CHINH LA IP cua Oppo A57!
    if joined_oppo_hs and gw_ip:
        res = scan_and_connect_single_ip(gw_ip)
        if res.get("connected"):
            return res

    # Kiem tra cac thiet bi dang ket noi vao Wi-Fi Hotspot Noi Bo cua Laptop ('Vuong' - dai 192.168.137.x)
    try:
        arp_out = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=4).stdout
        hotspot_ips = re.findall(r"(192\.168\.137\.\d+)", arp_out)
        for hip in hotspot_ips:
            if not hip.endswith(".1") and not hip.endswith(".255"):
                res = scan_and_connect_single_ip(hip)
                if res.get("connected"):
                    return res
    except Exception:
        pass

    cfg = get_settings()
    last_ip = (cfg.get("oppo_last_ip") or "").split(":")[0]
    if last_ip:
        res = scan_and_connect_single_ip(last_ip)
        if res.get("connected"):
            return res

    # Quet cong 5555 tren dai subnet hien tai cua Laptop
    subnet = get_laptop_subnet_prefix()

    def probe_subnet_host(host_idx: int):
        ip_cand = f"{subnet}.{host_idx}"
        try:
            s = socket.create_connection((ip_cand, 5555), 0.1)
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
            SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"connected": True, "serial": addr, "mode": "WIFI_ROAMING_AUTO", "detail": f"Tự động tìm thấy Oppo A57 ở mạng mới ({addr})"}

    return quick_check_oppo_connected()


def ensure_laptop_hotspot_on() -> dict:
    """Tu dong bat Diem phat song di dong (Windows Mobile Hotspot: SSID 'Vuong') va khoi dong lai SharedAccess DHCP (192.168.137.1)."""
    ps_script = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$cp = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile(); "
        "if ($cp -ne $null) { "
        "$tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($cp); "
        "$cfg = $tm.GetCurrentAccessPointConfiguration(); "
        "if ($tm.TetheringOperationalState -ne 'On') { "
        "$null = $tm.StartTetheringAsync(); Start-Sleep -Seconds 3; "
        "Restart-Service SharedAccess -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 "
        "} else { "
        "$ip = (Get-NetIPAddress -InterfaceAlias 'Local Area Connection* *' -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress; "
        "if (-not $ip) { Restart-Service SharedAccess -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 } "
        "}; "
        "Write-Output ($cfg.Ssid + '|' + $cfg.Passphrase + '|' + $tm.TetheringOperationalState) }"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, timeout=12)
        parts = r.stdout.strip().split("|")
        if len(parts) >= 2:
            return {"ok": True, "ssid": parts[0], "password": parts[1], "state": parts[2] if len(parts) > 2 else "On"}
    except Exception:
        pass
    return {"ok": False, "ssid": "Vuong", "password": "vuong2002", "state": "Unknown"}


def pair_oppo_wireless(pair_ip_port: str, pair_code: str, main_ip_port: str = "") -> dict:
    pair_ip_port = (pair_ip_port or "").strip()
    pair_code = (pair_code or "").strip()
    main_ip_port = (main_ip_port or "").strip()
    if not pair_ip_port or not pair_code:
        return {"ok": False, "message": "Vui lòng nhập đầy đủ IP:Port ghép nối và Mã 6 số."}

    ip_only = pair_ip_port.split(":")[0]
    try:
        p_num = int(pair_ip_port.split(":")[1])
        s = socket.create_connection((ip_only, p_num), 2.0)
        s.close()
    except Exception:
        hs = ensure_laptop_hotspot_on()
        return {
            "ok": False,
            "message": (
                f"⚠️ Router Wi-Fi công ty/quán hiện tại đang bật 'Cách ly thiết bị (AP Isolation)' nên chặn kết nối từ Laptop tới {pair_ip_port}! "
                f"Đã tự động bật Wi-Fi Nội Bộ trực tiếp trên Laptop của bạn: Tên Wi-Fi = '{hs['ssid']}' | Mật khẩu = '{hs['password']}'. "
                f"👉 Bạn chỉ cần mở Wi-Fi trên Oppo A57 -> Kết nối vào Wi-Fi '{hs['ssid']}' (mật khẩu: {hs['password']}) là Oppo A57 sẽ TỰ ĐỘNG KẾT NỐI NGAY mà không cần nhập mã!"
            ),
        }

    rc, out, err = run_adb(["pair", pair_ip_port, pair_code], timeout=10)
    combined = f"{out}\n{err}".strip()
    if "successfully paired" in combined.lower():
        cfg = get_settings()
        cfg["oppo_last_ip"] = ip_only
        SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        if main_ip_port:
            target_conn = main_ip_port if ":" in main_ip_port else f"{ip_only}:{main_ip_port}"
            conn = auto_connect_oppo(hint_ip=target_conn)
        else:
            conn = scan_and_connect_single_ip(ip_only)
        return {
            "ok": True,
            "message": f"✓ Ghép nối mã 6 số thành công ({combined})! {conn.get('detail', '')}",
            "connection": conn,
        }
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


def copy_vietnamese_to_oppo_clipboard(serial: str, item_id: str) -> bool:
    """
    Nap 100% Caption Tieng Viet CO DAU + 5 Hashtag vao Clipboard he thong cua Oppo A57
    qua duong ham ADB Reverse (http://127.0.0.1:8099/auto_copy) -> Khong phu thuoc Wi-Fi truong/quan cafe!
    """
    run_adb(["reverse", "tcp:8099", "tcp:8099"], serial=serial)
    url = f"http://127.0.0.1:8099/auto_copy?id={urllib.parse.quote(item_id)}"
    run_adb(["shell", "input", "keyevent", "224"], serial=serial)
    run_adb(["shell", "cmd", "statusbar", "collapse"], serial=serial)
    run_adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url], serial=serial)
    time.sleep(2.4)
    # Cham giua man hinh (360, 800) tren nut Full-Screen de Chrome copy 100% Unicode Tieng Viet vao Clipboard Android!
    run_adb(["shell", "input", "tap", "360", "800"], serial=serial)
    time.sleep(0.8)
    return True


def ensure_correct_tiktok_account(serial: str, target_handle: str) -> tuple[bool, str]:
    clean_handle = target_handle.lstrip("@").lower()
    run_adb(["shell", "input", "keyevent", "224"], serial=serial)
    run_adb(["shell", "cmd", "statusbar", "collapse"], serial=serial)
    time.sleep(0.5)

    run_adb(["shell", "am", "start", "-n", TIKTOK_SPLASH], serial=serial)
    time.sleep(3.2)

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
    time.sleep(2.4)

    nodes = dump_oppo_ui(serial)
    screen_text = " ".join((n["text"] + " " + n["desc"]).lower() for n in nodes)
    if f"@{clean_handle}" in screen_text or clean_handle in screen_text:
        return True, f"✓ Đã xác nhận Oppo A57 đang ở đúng tài khoản @{clean_handle}"

    switcher_btn = next((n for n in nodes if n["id"].endswith(":id/tjz") and n["cx"] > 0), None)
    if switcher_btn:
        run_adb(["shell", "input", "tap", str(switcher_btn["cx"]), str(switcher_btn["cy"])], serial=serial)
    else:
        run_adb(["shell", "input", "tap", "250", "231"], serial=serial)
    time.sleep(2.4)

    sheet_nodes = dump_oppo_ui(serial)
    sheet_blob = " ".join((n["text"] + " " + n["desc"]).lower() for n in sheet_nodes)
    # Neu man hinh hien tai da la trang Ho so cua dung @clean_handle -> Xac nhan thanh cong ngay!
    if f"@{clean_handle}" in sheet_blob:
        return True, f"✓ Đã xác nhận Oppo A57 đang ở đúng tài khoản @{clean_handle}"

    # Neu bang 'Chuyển đổi tài khoản' chua mo ra (do cu cham truoc vua dong popup), cham lai tab Ho so -> cham id/tjz (250, 231)
    if "chuyển đổi tài khoản" not in sheet_blob:
        run_adb(["shell", "input", "tap", "648", "1563"], serial=serial)
        time.sleep(2.0)
        p_nodes = dump_oppo_ui(serial)
        p_blob = " ".join((n["text"] + " " + n["desc"]).lower() for n in p_nodes)
        if f"@{clean_handle}" in p_blob:
            return True, f"✓ Đã xác nhận Oppo A57 đang ở đúng tài khoản @{clean_handle}"
        run_adb(["shell", "input", "tap", "250", "231"], serial=serial)
        time.sleep(2.4)
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
    time.sleep(3.8)
    return True, f"✓ Đã tự động chuyển sang đúng tài khoản @{clean_handle} trên Oppo A57!"


def prepare_single_clean_video_on_oppo(serial: str, local_video_path: Path) -> tuple[bool, str]:
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


def auto_save_draft_on_oppo(item_id: str = None, channel: str = None) -> dict:
    """
    LUONG TU DONG LUU NHAP (AUTO-SAVE-DRAFT) KEM CAPTION TIENG VIET CO DAU 100%:
    1. Kiem tra Chong Dang Trung 3 Lop (SHA-256)
    2. Nap Caption Tieng Viet CO DAU 100% vao Clipboard cua Oppo A57 (qua /auto_copy + tap 360,800)
    3. Mo TikTok & Chuyen sang DUNG tai khoan (@suckhoeviet.2 hoac @suc.khoe.vang.268)
    4. Xoa sach video cu trong Camera & Day DUY NHAT 1 video (.mp4) cua bai nay vao vị trí #1 Camera
    5. Bam '+' (360, 1563) -> Mo Thu vien (80, 1544) -> Chon video #1 (121, 371) -> Bam 'Tiếp' -> Bam 'Tiếp'
    6. Cham o 'Thêm mô tả...' (221, 324) -> Gui KEYCODE_PASTE (279) de dan NGUYEN VAN Caption Tieng Viet CO DAU + 5 Hashtag!
    7. Dong ban phim (keyevent 4) -> Bam nut 'Nháp' (com.ss.android.ugc.trill:id/gqm tai 188, 1540) de LUU NHAP!
    8. Danh dau trang thai 'SAVED_DRAFT' (📝 Đã Lưu Nháp) de khi den gio nhac (moi 1 tieng), nguoi dung chi can mo Nhap -> Chon San Pham -> Bam Dang!
    """
    conn_info = auto_connect_oppo()
    if not conn_info["connected"]:
        return {"ok": False, "step": "CONNECT_OPPO", "message": conn_info["detail"]}

    serial = conn_info["serial"]
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
        return {"ok": False, "message": "Không tìm thấy video sẵn sàng trong kho Cache Offline trên Laptop."}

    item, local_mp4 = candidate
    target_ch = item["channel"]

    # 1. Kiem tra Chong Dang Trung 3 Lop
    is_safe, dup_msg, f_hash, c_hash = check_duplicate_guard(item, local_mp4)
    if not is_safe:
        return {"ok": False, "step": "ANTI_DUPLICATE_GUARD", "message": dup_msg, "item": item}

    # 2. Copy Caption Tieng Viet CO DAU 100% vao Clipboard Laptop & Clipboard Oppo A57
    try:
        subprocess.run(["clip"], input=item["caption_seo"].encode("utf-16le"), check=False)
    except Exception:
        pass
    copy_vietnamese_to_oppo_clipboard(serial, item["id"])

    # 3. Mo TikTok & Chuyen sang dung tai khoan trong 4 tai khoan
    sw_ok, sw_msg = ensure_correct_tiktok_account(serial, target_ch)
    if not sw_ok:
        return {"ok": False, "step": "SWITCH_ACCOUNT", "message": sw_msg, "item": item}

    # 4. Xoa video cu & Day duy nhat 1 video moi sang Camera Oppo A57
    push_ok, remote_path = prepare_single_clean_video_on_oppo(serial, local_mp4)
    if not push_ok:
        return {"ok": False, "step": "PUSH_SINGLE_VIDEO", "message": remote_path}

    # 5. Bam nut '+' (Quay: 360, 1563)
    run_adb(["shell", "input", "tap", "360", "1563"], serial=serial)
    time.sleep(3.2)

    nodes = dump_oppo_ui(serial)
    if has_captcha_on_screen(nodes):
        return {"ok": False, "step": "CAPTCHA_PAUSE", "message": "TikTok hiện CAPTCHA trên Oppo A57. Vui lòng kéo xác thực trên màn hình điện thoại."}

    # Truong hop 1: Neu TikTok mo vao tab TẠO (co nut 'Video mới' id/q7u tai 266, 444) -> Bam 'Video mới' (266, 444) -> Chon o video #1 (360, 380)
    video_moi_btn = next((n for n in nodes if n["id"].endswith(":id/q7u") or n["text"] == "Video mới"), None)
    has_upload_area = any(n["id"].endswith(":id/upload_hot_area") or n["id"].endswith(":id/d9o") for n in nodes)

    if video_moi_btn:
        cx = video_moi_btn["cx"] if video_moi_btn["cx"] > 0 else 266
        cy = video_moi_btn["cy"] if video_moi_btn["cy"] > 0 else 444
        run_adb(["shell", "input", "tap", str(cx), str(cy)], serial=serial)
        time.sleep(2.5)
        run_adb(["shell", "input", "tap", "360", "380"], serial=serial)
    elif has_upload_area:
        # Truong hop 2: Man hinh Camera -> Bam upload_hot_area (80, 1544) -> Chon o #1 (121, 371)
        run_adb(["shell", "input", "tap", "80", "1544"], serial=serial)
        time.sleep(2.5)
        run_adb(["shell", "input", "tap", "121", "371"], serial=serial)
    else:
        # Truong hop 3: Tab ĐĂNG (o #1 la Máy ảnh 121,341 -> Video #1 nam o o #2: 360, 380)
        run_adb(["shell", "input", "tap", "360", "380"], serial=serial)
    time.sleep(3.5)

    # 6. Tren man hinh Editor (video dang phat 30fps nen KHONG goi uiautomator dump de tranh bi cho 10s idle!):
    # Bam thang nut 'Tiếp' (532, 1546) de sang trang Soan Mo Ta / Luu Nhap tinh!
    run_adb(["shell", "input", "tap", "532", "1546"], serial=serial)
    time.sleep(3.5)

    # Kiem tra xem da sang trang Soan Mo Ta (co id/hgl hoac id/gqm) chua; neu con o Editor thi bam 'Tiếp' (532, 1546) lan nua
    post_check = dump_oppo_ui(serial)
    if not any(n["id"].endswith(":id/hgl") or n["id"].endswith(":id/gqm") or "mô tả" in n["text"].lower() for n in post_check):
        run_adb(["shell", "input", "tap", "532", "1546"], serial=serial)
        time.sleep(3.2)

    # 7. Cham vao o 'Thêm mô tả...' (221, 324) va DAN (KEYCODE_PASTE = 279) Caption Tieng Viet CO DAU 100%!
    run_adb(["shell", "input", "tap", "221", "324"], serial=serial)
    time.sleep(1.2)
    run_adb(["shell", "input", "keyevent", "279"], serial=serial)  # KEYCODE_PASTE (Dan 100% Tieng Viet co dau tu Clipboard!)
    time.sleep(1.4)
    # Dong ban phim / bang goi y hashtag de hien nut 'Nháp' (188, 1540)
    run_adb(["shell", "input", "keyevent", "4"], serial=serial)
    time.sleep(1.2)

    # 8. Bam nut 'Nháp' (com.ss.android.ugc.trill:id/gqm tai 188, 1540)
    run_adb(["shell", "input", "tap", "188", "1540"], serial=serial)
    time.sleep(2.5)

    # LOP 4 CHONG TRUNG: Xoa ngay file video tam trong /sdcard/DCIM/Camera/ cua Oppo A57 sau khi TikTok da luu vao Nhap
    # -> Dam bao trong cuon Camera dien thoai KHONG BAO GIO con ton đọng video cu de chon nham!
    run_adb(
        ["shell", "rm -f /sdcard/DCIM/Camera/AUTO_*.mp4 /sdcard/DCIM/Camera/TIKTOK_CURRENT_*.mp4"],
        serial=serial,
    )

    # KHOA NGAY VAO SO CAI CHONG DANG TRUNG 3 LOP (anti_duplicate_ledger.db) NGAY KHI LUU NHAP
    # de video nay KHONG BAO GIO bi day hoac luu nhap lai lan thu 2!
    record_posted_in_ledger(item, f_hash, c_hash, mode="SAVED_DRAFT_LOCKED")

    # Cap nhat trang thai 'SAVED_DRAFT' trong local_queue.json (vẫn hiện trên bảng để chờ bạn bấm 'Đánh dấu Đã Đăng' từ Nháp)
    for x in queue:
        if x.get("id") == item["id"]:
            x["status"] = "SAVED_DRAFT"
            x["drafted_at"] = time.strftime("%H:%M · %d/%m/%Y")
            x["file_sha256"] = f_hash
    LOCAL_QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "step": "SAVED_TO_TIKTOK_DRAFTS",
        "message": (
            f"📝 ĐÃ LƯU NHÁP & KHÓA CHỐNG TRÙNG THÀNH CÔNG trên kênh {target_ch} "
            f"(Video: {local_mp4.name} • Mã SHA-256: {f_hash[:12]}... đã khóa cứng • Đã dọn sạch file thừa trong Camera Oppo A57)! "
            f"Khi đến giờ nhắc lịch (mỗi 1 tiếng), bạn chỉ cần mở mục [Nháp] trên Oppo A57 -> Chọn Sản Phẩm ({item['product_name']}) -> Bấm [Đăng]!"
        ),
        "item": item,
    }


def mark_video_as_posted(item_id: str) -> dict:
    """
    Khi nguoi dung mo Nhap, chon san pham va bam Dang xong -> Bam '[✅ Đánh Dấu Đã Đăng]':
    - Cap nhat trang thai trong So cai Chong Dang Trung = PUBLISHED_FROM_DRAFT
    - Xoa luon file .mp4 da dang khoi C:\\TikTok_AutoHub\\video_cache\\ de tiet kiem o C: va triet tieu 100% nguy co dang lai
    - Chuyen status = POSTED va bat dau dem nguoc 60 phut (1 tieng) cho luot nhac tiep theo!
    """
    if not LOCAL_QUEUE_FILE.exists():
        return {"ok": False, "message": "Không tìm thấy local_queue.json"}

    queue = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    target_item = next((x for x in queue if x.get("id") == item_id), None)
    if not target_item:
        return {"ok": False, "message": f"Không tìm thấy bài có mã {item_id}"}

    fname = Path(target_item.get("output_video", "")).name
    local_mp4 = CACHE_DIR / fname

    from anti_dup_sync import DB_PATH, init_db, sha256_file, sha256_text
    import sqlite3
    init_db()
    f_hash = target_item.get("file_sha256") or (sha256_file(local_mp4) if local_mp4.exists() else "LOCKED_SHA256")
    c_hash = sha256_text(target_item.get("caption_seo", ""))

    # Neu chua co trong ledger thi ghi moi; neu da khoa luc SAVED_DRAFT thi nang cap trang thai len PUBLISHED_FROM_DRAFT
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT id FROM posted_history WHERE item_id = ?", (item_id,))
    if cur.fetchone():
        cur.execute(
            "UPDATE posted_history SET post_mode = ?, posted_at = ? WHERE item_id = ?",
            ("PUBLISHED_FROM_DRAFT", time.strftime("%Y-%m-%d %H:%M:%S"), item_id),
        )
        conn.commit()
        conn.close()
    else:
        conn.close()
        record_posted_in_ledger(target_item, f_hash, c_hash, mode="PUBLISHED_FROM_DRAFT")

    for x in queue:
        if x.get("id") == item_id:
            x["status"] = "POSTED"
            x["posted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    LOCAL_QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    # Xoa file video .mp4 da dang khoi video_cache de KHONG BAO GIO con file tren may!
    try:
        if local_mp4.exists():
            local_mp4.unlink()
    except Exception:
        pass

    return {
        "ok": True,
        "message": (
            f"✅ Đã xác nhận ĐÃ ĐĂNG hoàn tất cho video '{fname}' trên kênh {target_item['channel']}! "
            f"Đã khóa vĩnh viễn mã SHA-256 ({f_hash[:14]}...), xóa file video gốc khỏi bộ đệm để chống đăng trùng tuyệt đối 100%, "
            f"và bắt đầu đếm ngược 60 phút (1 tiếng) để nhắc bài tiếp theo."
        ),
        "item": target_item,
        "file_sha256": f_hash,
    }
