# -*- coding: utf-8 -*-
"""
TIKTOK AUTOHUB MASTER CONTROL CENTER v3.0
- Giao dien chia 4 Tab chuyen nghiep, gon gang, de nhin.
- Thanh Dan Duong Full Flow 4 Buoc + Hop Goi Y Thong Minh (Smart Flow Coach).
- Phan hoi tuc thi (Instant Loading Modal + Dong ho dem giay + Live Step Logs + Toast Notification) cho MOI thao tac.
- Tu dong quan ly Cloudflare Tunnel doc lap ngay tren Laptop (tiktok-laptop-master):
  + https://master.phamvuong.io.vn -> http://127.0.0.1:8099 (Dieu khien Laptop nay tu xa khi di du lich)
  + https://idrac.phamvuong.io.vn & https://idrac-rescue.phamvuong.io.vn -> https://192.168.1.11 (Cuu ho iDRAC R620 truc tiep tu Laptop, khong phu thuoc VM100 hay Server)
  + https://pve-rescue.phamvuong.io.vn -> https://192.168.1.20:8006 (Cuu ho Proxmox truc tiep tu Laptop)
"""
import ctypes
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from anti_dup_sync import (
    ALLOWED_CHANNELS,
    CACHE_DIR,
    DATA_DIR,
    HUB_DIR,
    LOCAL_QUEUE_FILE,
    SETTINGS_FILE,
    get_ledger_history,
    get_settings,
    init_db,
    sync_from_r630_to_laptop_cache,
)
from oppo_auto_poster import (
    auto_connect_oppo,
    auto_save_draft_on_oppo,
    ensure_correct_tiktok_account,
    ensure_laptop_hotspot_on,
    get_laptop_lan_ip,
    mark_video_as_posted,
    pair_oppo_wireless,
    quick_check_oppo_connected,
    scan_and_connect_single_ip,
)
from home_server_bridge import get_bridge_status, start_cloudflare_login_and_ssh_tunnel
from local_video_editor import (
    EDITOR_STATUS,
    PRODUCT_CATALOG,
    add_custom_product,
    change_video_item_product,
    load_custom_products,
    start_batch_fetch_and_edit,
)

PORT = 8099
IDRAC_PROXY_PORT = 8098
IDRAC_HOST = "192.168.1.11"
CLOUDFLARED_EXE = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
LAPTOP_CF_CONFIG = DATA_DIR / "cloudflared" / "config.yml"
LAPTOP_CF_PROC = None


class IdracRescueProxyHandler(BaseHTTPRequestHandler):
    """
    Cau noi TLSv1.2 (DHE-RSA-AES256-GCM-SHA384) truc tiep tu Laptop (127.0.0.1:8098)
    sang Dell iDRAC7 R620 (https://192.168.1.11:443):
    - Khac phuc loi Go cloudflared khong ho tro cipher DHE cua iDRAC7.
    - Tu dong chuyen Location: https://192.168.1.11/... thanh duong dan tuong doi /...
      de khi di du lich truy cap qua https://idrac.phamvuong.io.vn khong bi vang ve IP LAN 192.168.1.11!
    """
    def log_message(self, format, *args):
        return

    def _proxy_to_idrac(self):
        import http.client
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers("ALL:@SECLEVEL=0")

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else None

        fwd_headers = {}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl in ("host", "origin", "referer", "connection", "transfer-encoding"):
                continue
            fwd_headers[k] = v
        fwd_headers["Host"] = IDRAC_HOST
        fwd_headers["Origin"] = f"https://{IDRAC_HOST}"
        fwd_headers["Referer"] = f"https://{IDRAC_HOST}/start.html"
        if "Accept-Encoding" not in fwd_headers and "accept-encoding" not in {x.lower() for x in fwd_headers}:
            fwd_headers["Accept-Encoding"] = "gzip, deflate"

        path = self.path or "/"
        if path == "/":
            path = "/start.html"

        try:
            conn = http.client.HTTPSConnection(IDRAC_HOST, 443, context=ctx, timeout=15)
            conn.request(self.command, path, body=body, headers=fwd_headers)
            resp = conn.getresponse()
            data = resp.read()

            self.send_response(resp.status)
            for hk, hv in resp.getheaders():
                hkl = hk.lower()
                if hkl in ("transfer-encoding", "connection", "content-length", "strict-transport-security"):
                    continue
                if hkl == "location":
                    hv = hv.replace(f"https://{IDRAC_HOST}", "").replace(f"http://{IDRAC_HOST}", "")
                    if not hv.startswith("/"):
                        hv = "/" + hv
                self.send_header(hk, hv)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
        except Exception as e:
            err_html = f"<h3>Không thể kết nối tới iDRAC {IDRAC_HOST}: {e}</h3>".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(err_html)))
            self.end_headers()
            self.wfile.write(err_html)

    def do_GET(self):
        self._proxy_to_idrac()

    def do_POST(self):
        self._proxy_to_idrac()

    def do_PUT(self):
        self._proxy_to_idrac()

    def do_DELETE(self):
        self._proxy_to_idrac()

    def do_HEAD(self):
        self._proxy_to_idrac()

RUNTIME_STATE = {
    "last_action_time": datetime.now().strftime("%H:%M:%S"),
    "last_action_result": "Trạm Kiểm Soát Master v3.0 đã sẵn sàng! Mọi thao tác đều có phản hồi trực tiếp theo thời gian thực.",
    "next_reminder_epoch": time.time() + 3600,
    "r630_sync_status": {"r630_online": False, "cached_offline_ready": 0, "total_queue": 0},
    "oppo_status": {"connected": False, "serial": None, "mode": "NONE", "detail": "Đang kiểm tra..."},
    "laptop_tunnel_active": False,
}

LIVE_ACTION = {
    "active": False,
    "title": "",
    "step": "Sẵn sàng",
    "started_epoch": 0,
    "logs": [
        f"[{datetime.now().strftime('%H:%M:%S')}] Hệ thống Master Control v3.0 khởi động thành công."
    ],
}


def push_live_log(msg: str, step: str = None):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    LIVE_ACTION["logs"].append(entry)
    if len(LIVE_ACTION["logs"]) > 60:
        LIVE_ACTION["logs"] = LIVE_ACTION["logs"][-60:]
    if step:
        LIVE_ACTION["step"] = step
    RUNTIME_STATE["last_action_time"] = ts
    RUNTIME_STATE["last_action_result"] = msg


def begin_live_action(title: str, initial_step: str):
    LIVE_ACTION["active"] = True
    LIVE_ACTION["title"] = title
    LIVE_ACTION["started_epoch"] = time.time()
    push_live_log(f"▶ BẮT ĐẦU: {title} — {initial_step}", step=initial_step)


def end_live_action(final_msg: str):
    push_live_log(final_msg, step=final_msg)
    LIVE_ACTION["active"] = False


def is_laptop_cloudflare_tunnel_running() -> bool:
    global LAPTOP_CF_PROC
    if LAPTOP_CF_PROC is not None and LAPTOP_CF_PROC.poll() is None:
        return True
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | Select-Object -ExpandProperty CommandLine"],
            capture_output=True,
            text=True,
            timeout=4,
        ).stdout
        return "tiktok-laptop-master" in (out or "").lower()
    except Exception:
        return False


def control_laptop_cloudflare_tunnel(enable: bool = True) -> dict:
    """
    Bat/Tat Cloudflare Tunnel doc lap ngay tren Laptop (tiktok-laptop-master):
    - https://master.phamvuong.io.vn -> http://127.0.0.1:8099
    - https://idrac.phamvuong.io.vn & https://idrac-rescue.phamvuong.io.vn -> https://192.168.1.11
    - https://pve-rescue.phamvuong.io.vn -> https://192.168.1.20:8006
    """
    global LAPTOP_CF_PROC
    if not enable:
        if LAPTOP_CF_PROC is not None:
            try:
                LAPTOP_CF_PROC.terminate()
            except Exception:
                pass
            LAPTOP_CF_PROC = None
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True)
        RUNTIME_STATE["laptop_tunnel_active"] = False
        msg = "⏹️ Đã TẮT đường hầm Cloudflare Từ Xa trên Laptop (master.phamvuong.io.vn & idrac.phamvuong.io.vn)."
        push_live_log(msg)
        return {"ok": True, "active": False, "message": msg}

    if is_laptop_cloudflare_tunnel_running():
        RUNTIME_STATE["laptop_tunnel_active"] = True
        msg = "✓ Đường hầm Cloudflare trên Laptop đang hoạt động: https://master.phamvuong.io.vn & https://idrac.phamvuong.io.vn"
        return {"ok": True, "active": True, "message": msg}

    if not Path(CLOUDFLARED_EXE).exists() or not LAPTOP_CF_CONFIG.exists():
        msg = f"⚠️ Không tìm thấy cloudflared.exe hoặc {LAPTOP_CF_CONFIG}"
        push_live_log(msg)
        return {"ok": False, "active": False, "message": msg}

    try:
        log_file = open(str(DATA_DIR / "cloudflared_laptop.log"), "a", encoding="utf-8")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        LAPTOP_CF_PROC = subprocess.Popen(
            [
                CLOUDFLARED_EXE,
                "tunnel",
                "--config",
                str(LAPTOP_CF_CONFIG),
                "run",
                "tiktok-laptop-master",
            ],
            stdout=log_file,
            stderr=log_file,
            creationflags=creation_flags,
        )
        time.sleep(1.5)
        RUNTIME_STATE["laptop_tunnel_active"] = is_laptop_cloudflare_tunnel_running()
        msg = (
            "✓ Đã BẬT đường hầm Cloudflare Từ Xa trực tiếp trên Laptop! "
            "Điều khiển Master từ xa: https://master.phamvuong.io.vn | Cứu hộ iDRAC 192.168.1.11: https://idrac.phamvuong.io.vn"
        )
        push_live_log(msg)
        return {"ok": True, "active": RUNTIME_STATE["laptop_tunnel_active"], "message": msg}
    except Exception as e:
        msg = f"⚠️ Lỗi khởi chạy Cloudflare Tunnel trên Laptop: {e}"
        push_live_log(msg)
        return {"ok": False, "active": False, "message": msg}


def check_idrac_lan_reachable() -> bool:
    try:
        import socket
        s = socket.create_connection(("192.168.1.11", 443), timeout=1.2)
        s.close()
        return True
    except Exception:
        return False


def popup_windows_reminder(title: str, message: str):
    """Phat chuong bao & hien bang Popup Nhac Dang Bai tren man hinh Windows Laptop."""
    def _alert():
        try:
            import winsound
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                time.sleep(0.35)
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x00001040)
        except Exception:
            pass

    threading.Thread(target=_alert, daemon=True).start()


def get_ready_queue_with_1h_schedule() -> list[dict]:
    if not LOCAL_QUEUE_FILE.exists():
        return []
    try:
        raw = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    ch1 = [x for x in raw if x.get("status") != "POSTED" and x.get("channel") == "@suckhoeviet.2"]
    ch2 = [x for x in raw if x.get("status") != "POSTED" and x.get("channel") == "@suc.khoe.vang.268"]

    interleaved = []
    max_len = max(len(ch1), len(ch2)) if (ch1 or ch2) else 0
    for i in range(max_len):
        if i < len(ch1):
            interleaved.append(ch1[i])
        if i < len(ch2):
            interleaved.append(ch2[i])

    base_time = datetime.now().replace(second=0, microsecond=0)
    for idx, item in enumerate(interleaved):
        slot_dt = base_time + timedelta(hours=idx)
        item["scheduled_1h_slot"] = (
            "Ngay bây giờ (Bài kế tiếp)" if idx == 0 else f"{slot_dt.strftime('%H:%M · %d/%m/%Y')} (Cách {idx}h)"
        )
        fname = Path(item.get("output_video", "")).name
        item["cached_offline"] = (CACHE_DIR / fname).exists()
    return interleaved


def trigger_1hour_draft_and_reminder() -> dict:
    begin_live_action("Tự động Lưu Nháp & Nhắc lịch 1 tiếng", "Đang kiểm tra hàng chờ video...")
    ready = get_ready_queue_with_1h_schedule()
    if not ready:
        end_live_action("⚠️ Không còn video nào trong hàng chờ.")
        return {"ok": False, "message": "Không còn video nào trong hàng chờ."}

    due_item = ready[0]
    draft_msg = "Video này đã được Lưu Nháp sẵn trên Oppo A57."
    res = {"ok": True, "item": due_item}

    oppo_now = quick_check_oppo_connected()
    if due_item.get("status") != "SAVED_DRAFT" and oppo_now.get("connected"):
        push_live_log(f"Đang đẩy video {due_item['id']} sang kênh {due_item['channel']} trên Oppo A57 & dán Caption Tiếng Việt...")
        res = auto_save_draft_on_oppo(item_id=due_item["id"])
        draft_msg = res.get("message", "")
    elif not oppo_now.get("connected"):
        draft_msg = "⚠️ Lưu ý: Oppo A57 chưa kết nối ADB nên hệ thống chưa tự bấm Lưu Nháp được. Hãy kết nối Oppo A57 để hệ thống tự động Lưu Nháp!"

    end_live_action(f"🔔 ĐẾN GIỜ ĐĂNG BÀI ({due_item['channel']}): {draft_msg}")

    popup_text = (
        f"⏰ ĐẾN KHUNG GIỜ ĐĂNG TIKTOK (1 TIẾNG / 1 VIDEO)!\n\n"
        f"• Tài khoản cần đăng: {due_item['channel']}\n"
        f"• Sản phẩm cần gắn giỏ hàng: {due_item['product_name']}\n"
        f"• Shop GMV Max: {due_item.get('seller_name', 'Shop GMV Max')}\n"
        f"• Trạng thái Nháp: {draft_msg}\n\n"
        f"👉 THAO TÁC TRÊN OPPO A57 (Chỉ 10 giây):\n"
        f"1. Mở TikTok trên Oppo A57 -> Vào Hồ sơ ({due_item['channel']}) -> Mở mục [Nháp]\n"
        f"2. Mở bài nháp trên cùng (đã có sẵn Video & Caption Tiếng Việt có dấu)\n"
        f"3. Chọn 'Thêm liên kết' -> Chọn sản phẩm '{due_item['product_name']}' -> Bấm [Đăng]\n"
        f"4. Bấm nút [✅ 2. Đánh Dấu Đã Đăng Từ Nháp] trên màn hình để khóa chống trùng!"
    )
    popup_windows_reminder("🔔 NHẮC LỊCH ĐĂNG TIKTOK (ĐÃ LƯU NHÁP TIẾNG VIỆT)", popup_text)
    return {
        "ok": True,
        "message": f"🔔 Đã nhắc lịch & xử lý Lưu Nháp cho kênh {due_item['channel']} ({due_item['product_name']})!",
        "draft_result": res,
    }


def background_scheduler_loop():
    time.sleep(2)
    try:
        RUNTIME_STATE["r630_sync_status"] = sync_from_r630_to_laptop_cache()
    except Exception:
        pass
    try:
        RUNTIME_STATE["oppo_status"] = quick_check_oppo_connected()
    except Exception:
        pass

    last_sync = time.time()
    while True:
        time.sleep(5)
        cfg = get_settings()
        RUNTIME_STATE["laptop_tunnel_active"] = is_laptop_cloudflare_tunnel_running()

        if time.time() - last_sync > 300:
            try:
                RUNTIME_STATE["r630_sync_status"] = sync_from_r630_to_laptop_cache()
            except Exception:
                pass
            last_sync = time.time()

        if not cfg.get("auto_scheduler_enabled", True):
            continue

        now = time.time()
        if now >= RUNTIME_STATE["next_reminder_epoch"]:
            interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
            RUNTIME_STATE["next_reminder_epoch"] = now + interval_sec
            trigger_1hour_draft_and_reminder()


class HubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, data: dict, status: int = 200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        client_ip = self.client_address[0]

        if client_ip not in ("127.0.0.1", "::1", get_laptop_lan_ip()):
            cfg = get_settings()
            if cfg.get("oppo_last_ip") != client_ip:
                cfg["oppo_last_ip"] = client_ip
                SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            if not quick_check_oppo_connected().get("connected"):
                threading.Thread(target=scan_and_connect_single_ip, args=(client_ip,), daemon=True).start()

        if parsed.path == "/api/live_progress":
            elapsed = int(time.time() - LIVE_ACTION["started_epoch"]) if LIVE_ACTION["active"] else 0
            return self._send_json({
                "active": LIVE_ACTION["active"],
                "title": LIVE_ACTION["title"],
                "step": LIVE_ACTION["step"],
                "elapsed_seconds": elapsed,
                "logs": LIVE_ACTION["logs"][-20:],
            })

        if parsed.path == "/api/status":
            cfg = get_settings()
            oppo = quick_check_oppo_connected()
            RUNTIME_STATE["oppo_status"] = oppo
            RUNTIME_STATE["laptop_tunnel_active"] = is_laptop_cloudflare_tunnel_running()
            ledger = get_ledger_history(40)
            ready_queue = get_ready_queue_with_1h_schedule()
            cached_count = sum(1 for x in ready_queue if x.get("cached_offline"))
            RUNTIME_STATE["r630_sync_status"]["cached_offline_ready"] = cached_count
            RUNTIME_STATE["r630_sync_status"]["total_queue"] = len(ready_queue)

            rem_sec = max(0, int(RUNTIME_STATE["next_reminder_epoch"] - time.time()))
            r630_svcs = {"tiktok-worker": True, "tiktok-portal": True, "cloudflared-tiktok": True}
            try:
                r630_base = cfg.get("r630_url", "https://tiktok.phamvuong.io.vn").rstrip("/")
                raw_s = urllib.request.urlopen(f"{r630_base}/api/r630_service_status", timeout=2.2).read().decode("utf-8")
                r630_svcs = json.loads(raw_s).get("services", r630_svcs)
            except Exception:
                pass
            return self._send_json({
                "settings": cfg,
                "lan_ip": get_laptop_lan_ip(),
                "runtime": RUNTIME_STATE,
                "live_action": {
                    "active": LIVE_ACTION["active"],
                    "title": LIVE_ACTION["title"],
                    "step": LIVE_ACTION["step"],
                    "elapsed_seconds": int(time.time() - LIVE_ACTION["started_epoch"]) if LIVE_ACTION["active"] else 0,
                    "logs": LIVE_ACTION["logs"][-25:],
                },
                "bridge": get_bridge_status(),
                "idrac_lan_ok": check_idrac_lan_reachable(),
                "r630_services": r630_svcs,
                "editor": EDITOR_STATUS,
                "next_wait_seconds": rem_sec,
                "ledger": ledger,
                "ready_queue": ready_queue[:60],
            })

        if parsed.path == "/auto_copy":
            item_id = qs.get("id", [""])[0]
            ready = get_ready_queue_with_1h_schedule()
            item = next((x for x in ready if x.get("id") == item_id), ready[0] if ready else None)
            cap = item["caption_seo"] if item else ""
            cap_json = json.dumps(cap, ensure_ascii=False)
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1"></head>
            <body style="margin:0;padding:0;background:#0b0f19;">
            <button id="fsbtn" onclick="doCopy()" style="width:100vw;height:100vh;background:#131b2e;color:#fde047;border:4px solid #fde047;font-size:22px;font-weight:bold;padding:24px;">
              CHẠM ĐỂ NẠP CAPTION TIẾNG VIỆT CÓ DẤU VÀO CLIPBOARD OPPO A57
            </button>
            <script>
            const TXT = {cap_json};
            function doCopy() {{
              if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(TXT);
              }}
              const ta = document.createElement('textarea');
              ta.value = TXT;
              document.body.appendChild(ta);
              ta.select();
              document.execCommand('copy');
              document.body.removeChild(ta);
              document.getElementById('fsbtn').style.background = '#166534';
              document.getElementById('fsbtn').textContent = '✓ ĐÃ COPY CAPTION TIẾNG VIỆT CÓ DẤU!';
            }}
            </script></body></html>"""
            raw = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path == "/video":
            fname = Path(qs.get("file", [""])[0]).name
            fpath = CACHE_DIR / fname
            if fpath.exists():
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", f'inline; filename="{fname}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, "Video not cached locally")
            return

        if parsed.path == "/mobile":
            item_id = qs.get("id", [""])[0]
            html = self._build_mobile_oppo_card_html(item_id, client_ip)
            raw = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        html = self._build_dashboard_html()
        raw = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length > 0 else {}

        if parsed.path == "/api/connect_oppo":
            hint = (body.get("ip_port") or "").strip() or None
            begin_live_action("Tìm & Kết nối ADB Oppo A57", f"Đang quét USB / mDNS / Wi-Fi LAN ({hint or 'Tự động'})...")
            res = auto_connect_oppo(hint_ip=hint)
            RUNTIME_STATE["oppo_status"] = res
            end_live_action(res.get("detail", "Đã kiểm tra kết nối Oppo A57"))
            return self._send_json(res)

        if parsed.path == "/api/pair_oppo":
            begin_live_action("Ghép nối Gỡ lỗi không dây Oppo A57", f"Đang ghép nối với {body.get('pair_ip_port', '')}...")
            res = pair_oppo_wireless(
                body.get("pair_ip_port", ""),
                body.get("pair_code", ""),
                body.get("main_ip_port", ""),
            )
            end_live_action(res.get("message", ""))
            return self._send_json(res)

        if parsed.path == "/api/sync_r630":
            begin_live_action("Đồng bộ Kho Video từ Server R630", "Đang kết nối tới R630 và tải video về bộ nhớ đệm Offline...")
            res = sync_from_r630_to_laptop_cache()
            RUNTIME_STATE["r630_sync_status"] = res
            msg = f"✓ Đồng bộ hoàn tất: {res['cached_offline_ready']}/{res['total_queue']} video đã sẵn sàng Offline trên Laptop (Tải mới: {res.get('downloaded_now', 0)} video)."
            end_live_action(msg)
            res["message"] = msg
            return self._send_json(res)

        if parsed.path == "/api/test_switch":
            ch = body.get("channel", "@suckhoeviet.2")
            begin_live_action(f"Chuyển tài khoản TikTok sang {ch}", "Đang kiểm tra kết nối ADB Oppo A57...")
            conn = auto_connect_oppo()
            if not conn["connected"]:
                end_live_action(conn["detail"])
                return self._send_json({"ok": False, "message": conn["detail"]})
            push_live_log(f"Đang mở TikTok trên Oppo A57 ({conn['serial']}) và chuyển tài khoản sang {ch}...")
            ok, msg = ensure_correct_tiktok_account(conn["serial"], ch)
            end_live_action(msg)
            return self._send_json({"ok": ok, "message": msg})

        if parsed.path == "/api/save_draft_on_oppo":
            item_id = body.get("item_id") or None
            ch = body.get("channel") or None
            begin_live_action(
                f"Tự động Đẩy Video + Dán Tiếng Việt & Lưu Nháp ({ch or 'Bài kế tiếp'})",
                "Bước 1/5: Kiểm tra chống trùng SHA-256 & kết nối ADB Oppo A57...",
            )
            push_live_log("Bước 2/5: Nạp Caption Tiếng Việt có dấu vào Clipboard Oppo A57 & chuyển đúng tài khoản TikTok...")
            res = auto_save_draft_on_oppo(item_id=item_id, channel=ch)
            end_live_action(res.get("message", "Hoàn tất thao tác Lưu Nháp"))
            return self._send_json(res)

        if parsed.path == "/api/mark_posted":
            item_id = body.get("item_id", "")
            begin_live_action("Xác nhận Đã Đăng & Khóa Chống Trùng SHA-256", f"Đang ghi sổ cái chống trùng cho {item_id}...")
            res = mark_video_as_posted(item_id)
            if res.get("ok"):
                cfg = get_settings()
                interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
                RUNTIME_STATE["next_reminder_epoch"] = time.time() + interval_sec
            end_live_action(res.get("message", ""))
            return self._send_json(res)

        if parsed.path == "/api/trigger_reminder_now":
            res = trigger_1hour_draft_and_reminder()
            return self._send_json(res)

        if parsed.path == "/api/start_remote_bridge":
            custom_wan = body.get("wan_ip_port", "")
            begin_live_action("Kiểm tra Kết nối Cloudflare R630 & Laptop", "Đang kiểm tra đường hầm phamvuong.io.vn...")
            res = start_cloudflare_login_and_ssh_tunnel(custom_wan)
            end_live_action(res.get("last_bridge_msg", ""))
            return self._send_json(res)

        if parsed.path == "/api/toggle_laptop_tunnel":
            enable = bool(body.get("enable", True))
            begin_live_action(
                "Điều khiển Đường Hầm Từ Xa Trên Laptop (Master & iDRAC 192.168.1.11)",
                "Đang bật/tắt tiến trình cloudflared.exe trên Laptop...",
            )
            res = control_laptop_cloudflare_tunnel(enable=enable)
            end_live_action(res.get("message", ""))
            return self._send_json(res)

        if parsed.path == "/api/fetch_edit_new_link":
            lv_url = body.get("livevault_url", "")
            max_c = int(body.get("max_clips", 5))
            p_key = body.get("product_key", "AUTO")
            begin_live_action("Thu & Edit Loạt Video Mới từ LiveVault", f"Đang khởi chạy tiến trình cắt {max_c} clip...")
            res = start_batch_fetch_and_edit(lv_url, max_clips=max_c, forced_product_key=p_key)
            end_live_action(res.get("message", ""))
            return self._send_json(res)

        if parsed.path == "/api/change_item_product":
            iid = body.get("item_id", "")
            pkey = body.get("product_key", "")
            begin_live_action(
                f"Đổi sản phẩm & Render lại bìa vàng ({pkey})",
                f"Đang dùng FFmpeg đóng lại khung bìa vàng mới và viết lại Caption SEO cho {iid}...",
            )
            res = change_video_item_product(iid, pkey)
            end_live_action(res.get("message", ""))
            return self._send_json(res)

        if parsed.path == "/api/add_custom_product":
            begin_live_action("Thêm sản phẩm mới vào Từ điển AI", "Đang lưu cấu hình sản phẩm...")
            res = add_custom_product(
                body.get("product_key", ""),
                body.get("product_name", ""),
                body.get("cover_title", ""),
                body.get("benefit_1", ""),
                body.get("benefit_2", ""),
                body.get("dosage", ""),
                body.get("keywords", ""),
            )
            end_live_action(res.get("message", ""))
            return self._send_json(res)

        if parsed.path == "/api/toggle_scheduler":
            cfg = get_settings()
            cfg["auto_scheduler_enabled"] = bool(body.get("enabled", True))
            if "interval_minutes" in body:
                cfg["interval_minutes"] = max(15, int(body["interval_minutes"]))
            SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            RUNTIME_STATE["next_reminder_epoch"] = time.time() + cfg["interval_minutes"] * 60
            state_txt = "▶️ ĐÃ BẬT Tự động Lưu Nháp & Nhắc lịch mỗi 1 tiếng" if cfg["auto_scheduler_enabled"] else "⏹️ ĐÃ TẮT Tự động Lưu Nháp & Nhắc lịch 1 tiếng"
            push_live_log(state_txt)
            return self._send_json({"ok": True, "settings": cfg, "message": state_txt})

        if parsed.path == "/api/r630_service_control":
            svc = body.get("service", "tiktok-worker")
            act = body.get("action", "restart")
            begin_live_action(f"Điều khiển dịch vụ R630 ({svc} -> {act})", "Đang gửi lệnh tới Container 240 trên Server R630...")
            cfg = get_settings()
            r630_base = cfg.get("r630_url", "https://tiktok.phamvuong.io.vn").rstrip("/")
            try:
                req = urllib.request.Request(
                    f"{r630_base}/api/r630_service?action={urllib.parse.quote(act)}&service={urllib.parse.quote(svc)}",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "User-Agent": "TikTok-AutoHub/3.0"},
                    method="POST",
                )
                resp = json.loads(urllib.request.urlopen(req, timeout=8).read().decode("utf-8"))
                msg = f"✓ Đã thực thi '{act.upper()}' cho dịch vụ '{svc}' trên Server R630!"
                end_live_action(msg)
                resp["message"] = msg
                return self._send_json(resp)
            except Exception as e:
                msg = f"⚠️ Không thể gửi lệnh tới R630 ({r630_base}): {e}"
                end_live_action(msg)
                return self._send_json({"ok": False, "message": msg})

        if parsed.path == "/api/local_service_control":
            act = body.get("action", "")
            if act == "restart_adb":
                begin_live_action("Khởi động lại kết nối ADB Oppo A57", "Đang chạy adb kill-server & start-server...")
                adb_exe = str(HUB_DIR / "tools" / "platform-tools" / "adb.exe")
                subprocess.run([adb_exe, "kill-server"], capture_output=True)
                time.sleep(0.5)
                subprocess.run([adb_exe, "start-server"], capture_output=True)
                res = auto_connect_oppo()
                RUNTIME_STATE["oppo_status"] = res
                msg = f"✓ Đã khởi động lại ADB Server: {res.get('detail', '')}"
                end_live_action(msg)
                return self._send_json({"ok": True, "message": msg})
            if act == "stop_hub":
                push_live_log("🛑 Đang tắt toàn bộ Trạm Kiểm Soát trên Laptop theo yêu cầu của bạn...")
                def _DelayedExit():
                    time.sleep(1.0)
                    control_laptop_cloudflare_tunnel(enable=False)
                    os._exit(0)
                threading.Thread(target=_DelayedExit, daemon=True).start()
                return self._send_json({
                    "ok": True,
                    "message": "🛑 Đã tắt Trạm Kiểm Soát Laptop & Đường hầm Cloudflare! Khi muốn bật lại, bạn nhấp đúp file Start-TikTok-AutoHub.cmd hoặc Master-Control-Station.cmd.",
                })

        self.send_error(404, "Not Found")

    def _build_mobile_oppo_card_html(self, item_id: str, client_ip: str) -> str:
        ready = get_ready_queue_with_1h_schedule()
        item = next((x for x in ready if x.get("id") == item_id), ready[0] if ready else None)
        if not item:
            return "<html><body style='background:#0b0f19;color:#fff;font-family:sans-serif;padding:20px;'><h2>Không còn bài nào trong hàng chờ</h2></body></html>"
        cap_json = json.dumps(item["caption_seo"], ensure_ascii=False)
        return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oppo A57 — Copy Tiếng Việt Có Dấu & Lưu Nháp</title>
<style>
  body {{ background:#090d16; color:#f8fafc; font-family:system-ui,sans-serif; padding:16px; margin:0; }}
  .box {{ background:#131b2e; border:2px solid #22c55e; border-radius:14px; padding:16px; margin-bottom:14px; }}
  .badge {{ display:inline-block; background:#fde047; color:#000; font-weight:800; padding:4px 10px; border-radius:99px; font-size:13px; margin-bottom:8px; }}
  .cap {{ background:#0b0f19; border:1px solid #334155; border-radius:10px; padding:12px; font-size:14px; white-space:pre-wrap; line-height:1.5; color:#e2e8f0; margin:10px 0; }}
  .btn {{ display:block; width:100%; padding:16px; border-radius:12px; border:none; font-size:17px; font-weight:800; text-align:center; text-decoration:none; margin-bottom:10px; cursor:pointer; box-sizing:border-box; }}
  .btn-copy {{ background:#eab308; color:#000; }}
</style>
</head>
<body>
  <div class="box">
    <div class="badge">✓ ĐÃ GHI NHẬN IP OPPO A57: {client_ip}</div>
    <h3 style="margin:4px 0 6px 0;color:#4ade80;">Kênh đích: {item['channel']}</h3>
    <div style="font-size:14px;color:#fde047;font-weight:700;">🛒 Sản phẩm cần chọn: {item['product_name']}</div>
    <div class="cap" id="capBox">{item['caption_seo']}</div>
    <button class="btn btn-copy" id="copyBtn" onclick="copyViet()">📋 COPY CAPTION TIẾNG VIỆT CÓ DẤU</button>
  </div>
<script>
const CAP_TEXT = {cap_json};
function copyViet() {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(CAP_TEXT);
  }}
  const ta = document.createElement('textarea');
  ta.value = CAP_TEXT;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  const b = document.getElementById('copyBtn');
  b.style.background = '#22c55e';
  b.style.color = '#fff';
  b.textContent = '✓ ĐÃ COPY TIẾNG VIỆT CÓ DẤU VÀO OPPO A57!';
}}
</script>
</body>
</html>"""

    def _build_dashboard_html(self) -> str:
        return r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trạm Kiểm Soát Master v3.0 — TikTok AutoHub & Cứu Hộ Từ Xa</title>
<style>
  :root {
    --bg: #070b14;
    --card: #101726;
    --card-alt: #151f33;
    --border: #24324d;
    --gold: #facc15;
    --green: #22c55e;
    --blue: #38bdf8;
    --purple: #a855f7;
    --red: #ef4444;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px 22px 60px 22px;
    background: var(--bg); color: var(--text);
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  }

  /* 1. LIVE EXECUTION FLOATING MODAL / PROGRESS OVERLAY */
  .live-overlay {
    display: none;
    position: fixed;
    top: 16px; left: 50%;
    transform: translateX(-50%);
    z-index: 9999;
    width: min(760px, 94vw);
    background: linear-gradient(135deg, #172554 0%, #0f172a 100%);
    border: 2px solid var(--gold);
    border-radius: 14px;
    padding: 16px 20px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.85);
  }
  .live-overlay.show { display: block; animation: slideDown 0.2s ease-out; }
  @keyframes slideDown { from { opacity: 0; transform: translate(-50%, -16px); } to { opacity: 1; transform: translate(-50%, 0); } }
  .spinner {
    display: inline-block;
    width: 18px; height: 18px;
    border: 3px solid rgba(250,204,21,0.25);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
    vertical-align: middle;
    margin-right: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* TOAST NOTIFICATION */
  .toast-container {
    position: fixed;
    bottom: 22px; right: 22px;
    z-index: 9998;
    display: flex; flex-direction: column; gap: 10px;
    max-width: 460px;
  }
  .toast {
    background: #0f172a;
    border-left: 5px solid var(--green);
    border-top: 1px solid #334155;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
    color: #fff;
    padding: 13px 16px;
    border-radius: 10px;
    font-size: 13.5px;
    line-height: 1.5;
    box-shadow: 0 12px 30px rgba(0,0,0,0.75);
  }
  .toast.error { border-left-color: var(--red); background: #1e1116; }

  /* HEADER */
  .top-header {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, #0f172a 0%, #172036 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px 20px;
    margin-bottom: 14px;
    gap: 12px;
  }
  .brand-title { font-size: 19px; font-weight: 800; color: var(--gold); letter-spacing: 0.3px; }
  .brand-sub { font-size: 12.5px; color: var(--muted); margin-top: 3px; }
  .pill-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .pill {
    padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: 700;
    border: 1px solid var(--border); background: #0b1120;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .pill.ok { background: rgba(34,197,94,0.13); color: #4ade80; border-color: #16a34a; }
  .pill.warn { background: rgba(250,204,21,0.13); color: #fde047; border-color: #ca8a04; }
  .pill.err { background: rgba(239,68,68,0.13); color: #f87171; border-color: #dc2626; }

  /* SMART FLOW STEPPER + COACH BANNER */
  .flow-banner {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 14px;
  }
  .stepper-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 12px;
  }
  @media (max-width: 1024px) { .stepper-grid { grid-template-columns: repeat(2, 1fr); } }
  .step-card {
    background: #0b111e;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 10px 12px;
    position: relative;
    transition: all 0.2s;
  }
  .step-card.done { border-color: #16a34a; background: rgba(22,163,74,0.08); }
  .step-card.active { border-color: var(--gold); background: rgba(250,204,21,0.1); box-shadow: 0 0 15px rgba(250,204,21,0.12); }
  .step-num {
    font-size: 11px; font-weight: 800; text-transform: uppercase;
    padding: 2px 8px; border-radius: 99px; display: inline-block; margin-bottom: 4px;
    background: #1e293b; color: #cbd5e1;
  }
  .step-card.done .step-num { background: #16a34a; color: #fff; }
  .step-card.active .step-num { background: var(--gold); color: #000; }
  .step-title { font-size: 13px; font-weight: 700; color: #f1f5f9; }
  .step-desc { font-size: 11.5px; color: var(--muted); margin-top: 3px; line-height: 1.35; }

  .smart-coach {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(250,204,21,0.14) 0%, rgba(56,189,248,0.1) 100%);
    border: 1px solid rgba(250,204,21,0.5);
    border-radius: 10px;
    padding: 10px 14px;
    gap: 10px;
  }
  .coach-text { font-size: 13.5px; color: #fef08a; font-weight: 600; line-height: 1.45; }

  /* LIVE FEEDBACK BAR (ALWAYS VISIBLE) */
  .status-strip {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    background: #0a101d;
    border: 1px solid #1e293b;
    border-left: 4px solid var(--blue);
    border-radius: 10px;
    padding: 9px 14px;
    margin-bottom: 14px;
    font-size: 13px;
    gap: 10px;
  }

  /* NAVIGATION TABS */
  .tabs-nav {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px;
  }
  .tab-btn {
    background: #111827;
    color: #cbd5e1;
    border: 1px solid var(--border);
    padding: 10px 18px;
    border-radius: 10px;
    font-size: 13.5px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s;
    display: inline-flex; align-items: center; gap: 8px;
  }
  .tab-btn:hover { border-color: #475569; color: #fff; }
  .tab-btn.active {
    background: var(--gold);
    color: #000;
    border-color: var(--gold);
    box-shadow: 0 4px 14px rgba(250,204,21,0.25);
  }
  .tab-badge {
    background: rgba(0,0,0,0.2);
    padding: 2px 7px; border-radius: 99px; font-size: 11px;
  }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }

  /* CARDS & GRIDS */
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
  .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 16px; }
  @media (max-width: 980px) { .grid-2, .grid-3 { grid-template-columns: 1fr; } }

  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px;
  }
  .card h3 {
    margin: 0 0 10px 0; font-size: 15px; color: #fff;
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
  }

  /* BUTTONS & INPUTS */
  .btn {
    cursor: pointer; border: none; border-radius: 9px;
    padding: 10px 14px; font-weight: 700; font-size: 13px;
    transition: all 0.15s; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    text-decoration: none;
  }
  .btn:disabled { opacity: 0.55; cursor: wait; }
  .btn:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); }
  .btn-gold { background: var(--gold); color: #000; }
  .btn-green { background: var(--green); color: #000; }
  .btn-blue { background: var(--blue); color: #000; }
  .btn-red { background: var(--red); color: #fff; }
  .btn-dark { background: #1e293b; color: #f8fafc; border: 1px solid #334155; }
  .input {
    background: #090d16; border: 1px solid #334155; color: #fff;
    padding: 9px 12px; border-radius: 8px; font-size: 13px; width: 100%;
  }

  /* TABLE */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 12px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
  th { color: var(--muted); font-size: 11.5px; text-transform: uppercase; background: #0b111e; position: sticky; top: 0; }
  .cap-preview {
    background: #090d16; border: 1px solid #1e293b; border-radius: 8px;
    padding: 9px 11px; font-size: 12.5px; color: #e2e8f0; white-space: pre-wrap; max-width: 430px; line-height: 1.45;
  }
  .cover-pill-preview {
    background: #facc15; color: #000; font-weight: 800; font-size: 12px;
    padding: 7px 10px; border-radius: 8px; text-align: center; white-space: pre-line;
    margin-bottom: 6px; line-height: 1.35;
  }
  .tag-ch1 { background: rgba(56,189,248,0.15); color: #38bdf8; padding: 3px 9px; border-radius: 6px; font-weight: 700; display: inline-block; }
  .tag-ch2 { background: rgba(168,85,247,0.18); color: #c084fc; padding: 3px 9px; border-radius: 6px; font-weight: 700; display: inline-block; }
  .draft-badge { background: rgba(250,204,21,0.2); color: #fde047; border: 1px solid #eab308; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; display: inline-block; margin-top: 4px; }

  /* SWITCH CARD IN TAB 2 */
  .sw-card {
    background: #0b111e; border: 1px solid var(--border); border-radius: 12px; padding: 14px;
    display: flex; flex-direction: column; justify-content: space-between;
  }
  .sw-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .sw-title { font-size: 14px; font-weight: 800; color: #f8fafc; }
  .sw-badge { font-size: 11px; font-weight: 800; padding: 3px 9px; border-radius: 99px; }
  .sw-badge.on { background: rgba(34,197,94,0.2); color: #4ade80; border: 1px solid #16a34a; }
  .sw-badge.off { background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid #dc2626; }
</style>
</head>
<body>

  <!-- 1. FLOATING LIVE EXECUTION MODAL (HIỆN NGAY LẬP TỨC KHI BẤM BẤT KỲ NÚT NÀO) -->
  <div class="live-overlay" id="liveOverlay">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <div style="font-size:15px;font-weight:800;color:var(--gold);">
        <span class="spinner"></span>
        <span id="liveTitle">Đang thực thi thao tác...</span>
      </div>
      <div style="background:#090d16;border:1px solid #475569;padding:3px 10px;border-radius:99px;font-size:12px;color:#38bdf8;font-weight:800;">
        ⏱️ Đã chạy: <span id="liveTimer">0</span>s
      </div>
    </div>
    <div id="liveStep" style="font-size:13px;color:#e2e8f0;margin-bottom:8px;font-weight:600;">
      Hệ thống đang xử lý, vui lòng đợi...
    </div>
    <div id="liveConsole" style="background:#050811;border:1px solid #1e293b;border-radius:8px;padding:8px 10px;font-family:Consolas,monospace;font-size:11.5px;color:#4ade80;max-height:110px;overflow-y:auto;line-height:1.45;">
    </div>
  </div>

  <!-- TOAST CONTAINER -->
  <div class="toast-container" id="toastContainer"></div>

  <!-- 2. TOP HEADER -->
  <div class="top-header">
    <div>
      <div class="brand-title">⚡ TIKTOK AUTOHUB — TRẠM KIỂM SOÁT MASTER v3.0</div>
      <div class="brand-sub">Tự động Lưu Nháp Tiếng Việt · Đổi Sản Phẩm 1 Chạm · Điều Khiển Từ Xa Khi Đi Du Lịch & Cứu Hộ iDRAC Độc Lập</div>
    </div>
    <div class="pill-row">
      <div class="pill warn" id="pillOppo">📱 Oppo A57: Đang kiểm tra...</div>
      <div class="pill ok" id="pillRemoteMaster">🌍 Master Từ Xa: master.phamvuong.io.vn</div>
      <div class="pill ok" id="pillIdrac">🛡️ Cứu Hộ iDRAC (192.168.1.11): Sẵn sàng</div>
      <div class="pill ok" id="pillCache">📦 Kho Video: 0 bài</div>
    </div>
  </div>

  <!-- 3. SMART FULL-FLOW 4-STEP GUIDE & NEXT ACTION COACH -->
  <div class="flow-banner">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <div style="font-size:13px;font-weight:800;color:#38bdf8;text-transform:uppercase;letter-spacing:0.4px;">
        🧭 Lộ Trình Chạy Full Flow 4 Bước Chuẩn (Tự Động Đánh Dấu Theo Trạng Thái Thực Tế)
      </div>
      <div style="font-size:12px;color:var(--muted);">
        Bạn chỉ cần nhìn bước nào đang sáng <b style="color:var(--gold);">MÀU VÀNG</b> và bấm theo hộp Gợi ý bên dưới!
      </div>
    </div>
    <div class="stepper-grid">
      <div class="step-card" id="stepCard1">
        <span class="step-num" id="stepNum1">Bước 1</span>
        <div class="step-title">1. Kết Nối Điện Thoại Oppo A57</div>
        <div class="step-desc" id="stepDesc1">Cắm cáp USB (hoặc bật Wi-Fi ADB) để Laptop điều khiển Oppo A57 xuyên suốt.</div>
      </div>
      <div class="step-card" id="stepCard2">
        <span class="step-num" id="stepNum2">Bước 2</span>
        <div class="step-title">2. Kiểm Tra Kho Video & Sản Phẩm</div>
        <div class="step-desc" id="stepDesc2">Kiểm tra sản phẩm bài kế tiếp. Nếu cần đổi, chọn menu Đổi Sản Phẩm để vẽ lại bìa.</div>
      </div>
      <div class="step-card" id="stepCard3">
        <span class="step-num" id="stepNum3">Bước 3</span>
        <div class="step-title">3. Tự Động Đẩy Video & Lưu Nháp</div>
        <div class="step-desc" id="stepDesc3">Bấm nút Lưu Nháp (hoặc để tự chạy mỗi 60p): Tự chuyển kênh, dán Tiếng Việt & bấm Nháp.</div>
      </div>
      <div class="step-card" id="stepCard4">
        <span class="step-num" id="stepNum4">Bước 4</span>
        <div class="step-title">4. Mở Nháp Gắn Giỏ Hàng & Khóa Trùng</div>
        <div class="step-desc" id="stepDesc4">Mở [Nháp] trên TikTok Oppo A57 -> Gắn sản phẩm GMV Max -> Đăng -> Bấm Đánh Dấu Đã Đăng.</div>
      </div>
    </div>

    <!-- HỘP GỢI Ý THÔNG MINH -->
    <div class="smart-coach">
      <div class="coach-text" id="coachText">
        💡 Đang phân tích trạng thái hệ thống để đưa ra gợi ý bước tiếp theo cho bạn...
      </div>
      <div id="coachActionBtnWrap">
        <button class="btn btn-gold" onclick="connectOppo()">🔌 Kết Nối Oppo A57 Ngay</button>
      </div>
    </div>
  </div>

  <!-- 4. LIVE FEEDBACK STRIP -->
  <div class="status-strip">
    <div>
      <strong style="color:#38bdf8;">📣 Phản hồi hệ thống mới nhất:</strong>
      <span id="lastActionText" style="color:#f1f5f9;margin-left:6px;">Đang tải trạng thái...</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center;">
      <span style="font-size:12px;color:var(--muted);" id="lastActionTime">--:--:--</span>
      <button class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" onclick="switchTab('tab4')">📜 Xem Nhật Ký Chi Tiết</button>
    </div>
  </div>

  <!-- 5. CLEAN 4-TAB NAVIGATION -->
  <div class="tabs-nav">
    <button class="tab-btn active" id="btn_tab1" onclick="switchTab('tab1')">
      🚀 1. Bảng Điều Khiển Chính & Lịch Đăng <span class="tab-badge" id="badgeQueueCount">0</span>
    </button>
    <button class="tab-btn" id="btn_tab2" onclick="switchTab('tab2')">
      🌍 2. Điều Khiển Từ Xa (Khi Đi Du Lịch) & Công Tắc Bật/Tắt
    </button>
    <button class="tab-btn" id="btn_tab3" onclick="switchTab('tab3')">
      🎬 3. Thu & Edit Link LiveVault Mới + Từ Điển Sản Phẩm
    </button>
    <button class="tab-btn" id="btn_tab4" onclick="switchTab('tab4')">
      🛡️ 4. Sổ Cái Chống Đăng Trùng (SHA-256) & Sơ Đồ Hệ Thống
    </button>
  </div>

  <!-- =====================================================================
       TAB 1: BẢNG ĐIỀU KHIỂN CHÍNH & LỊCH ĐĂNG HÀNG NGÀY
       ===================================================================== -->
  <div class="tab-pane active" id="tab1">
    <!-- HỘP DÁN LINK THU & CHẠY TỰ ĐỘNG TOÀN TRÌNH NGAY ĐẦU TAB 1 -->
    <div class="card" style="margin-bottom:14px;border:2px solid var(--gold);background:linear-gradient(135deg, #101726 0%, #172036 100%);">
      <h3>
        <span style="color:var(--gold);font-size:16px;">🚀 Dán Link Thu Vào Đây Để Chạy Tự Động Toàn Trình (Thu -> Cắt Bìa Vàng -> Lên Lịch -> Đẩy Lưu Nháp Oppo A57)</span>
        <span id="quickEditorPct" style="font-size:13px;background:#166534;color:#4ade80;padding:3px 10px;border-radius:99px;font-weight:800;">SẴN SÀNG</span>
      </h3>
      <div style="font-size:12.5px;color:#cbd5e1;margin-bottom:10px;line-height:1.45;">
        Bạn chỉ cần dán <b>Link Thu LiveVault</b> (vd: <code>http://192.168.1.75:8090/d/...</code>) hoặc <b>Link Livestream TikTok</b> (<code>https://www.tiktok.com/@.../live</code>) vào ô bên dưới rồi bấm nút, hoặc bấm <b>"⚡ Tự Lấy Phiên Ghi Mới Nhất Trong Máy"</b> — mọi bước từ nhận diện giọng nói 8 sản phẩm, đóng bìa vàng 2 kênh, đưa lên đầu lịch đến tự đẩy sang Oppo A57 & Lưu Nháp Tiếng Việt sẽ tự chạy 100%:
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px;">
        <input class="input" id="quickLvUrlInput" style="flex:2.4;min-width:260px;border-color:var(--gold);font-size:13.5px;" placeholder="Dán link thu (http://...:8090/d/... hoặc link TikTok Live)... Bỏ trống để tự lấy phiên ghi mới nhất trong máy!">
        <select class="input" id="quickLvMaxClips" style="flex:0.8;min-width:155px;">
          <option value="3">Cắt 3 clip (6 video)</option>
          <option value="5" selected>Cắt 5 clip (10 video)</option>
          <option value="10">Cắt 10 clip (20 video)</option>
          <option value="25">Cắt 25 clip (50 video)</option>
        </select>
        <select class="input" id="quickLvProductKey" style="flex:1.1;min-width:210px;">
          <option value="AUTO" selected>🤖 AI Tự nhận diện giọng nói (8 SP)</option>
          <option value="marial_gel">Marial Gel Ý (Bao tử & Trào ngược)</option>
          <option value="ginkgo_bonao">Ginkgo Biloba Mỹ (Dưỡng não, Tiền đình)</option>
          <option value="canxi_mason">Canxi hữu cơ Mỹ Mason (Tê tay, chuột rút)</option>
          <option value="bokhop_chondro">Bổ khớp Chondro-Aid Pháp (Đau khớp gối)</option>
          <option value="omega3_arko">Dầu cá Omega 3 Pháp (Mỡ máu, khô mắt)</option>
          <option value="vitamin_azinc">Vitamin Azinc 3B Pháp (Mệt mỏi, thần kinh tọa)</option>
          <option value="collagen_chalpha">Collagen sụn khớp CH-Alpha Đức</option>
          <option value="biotin_forcapil">Biotin Forcapil Pháp (Rụng tóc)</option>
        </select>
        <button class="btn btn-gold" style="padding:10px 18px;font-size:13.5px;" onclick="startQuickBatchEdit(false, this)">
          🚀 Chạy Tự Động Toàn Trình Ngay
        </button>
        <button class="btn btn-green" style="padding:10px 14px;font-size:13px;" onclick="startQuickBatchEdit(true, this)">
          ⚡ Tự Lấy Phiên Ghi Mới Nhất
        </button>
      </div>
      <div style="background:#090d16;border:1px solid #1e293b;border-radius:8px;padding:8px 12px;">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px;">
          <span id="quickEditorStep" style="color:#fde047;font-weight:700;">Sẵn sàng nhận link thu mới để chạy tự động toàn trình.</span>
          <span id="quickEditorPctNum" style="color:#4ade80;font-weight:800;">0%</span>
        </div>
        <div style="width:100%;height:7px;background:#1e293b;border-radius:99px;overflow:hidden;">
          <div id="quickEditorBar" style="width:0%;height:100%;background:linear-gradient(90deg,#facc15,#22c55e);transition:width 0.3s;"></div>
        </div>
      </div>
    </div>

    <div class="grid-2">
      <!-- HỘP TRÁI: KẾT NỐI OPPO A57 & CHUYỂN TÀI KHOẢN -->
      <div class="card">
        <h3>
          <span>📱 Kết Nối Điện Thoại Oppo A57 & Chuyển Kênh</span>
          <span id="oppoModeBadge" style="font-size:11.5px;color:#4ade80;font-weight:700;">--</span>
        </h3>
        <div id="oppoDetailBox" style="font-size:12.5px;color:#cbd5e1;background:#090d16;border:1px solid #1e293b;border-radius:8px;padding:9px 12px;margin-bottom:10px;">
          Đang kiểm tra kết nối Oppo A57...
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
          <button class="btn btn-gold" style="flex:1;" onclick="connectOppo(this)">
            🔌 Tự Động Tìm & Nối Oppo A57 (USB / Wi-Fi)
          </button>
          <button class="btn btn-dark" onclick="testSwitch('@suckhoeviet.2', this)">
            🔄 Chuyển @suckhoeviet.2
          </button>
          <button class="btn btn-dark" onclick="testSwitch('@suc.khoe.vang.268', this)">
            🔄 Chuyển @suc.khoe.vang.268
          </button>
        </div>
        <details style="background:#090d16;border:1px solid #1e293b;border-radius:8px;padding:8px 12px;font-size:12px;">
          <summary style="cursor:pointer;color:#38bdf8;font-weight:700;">
            ⚙️ Mở Cài Đặt Kết Nối IP:Port Không Dây / Mã Ghép Nối 6 Số (Chỉ dùng khi rút cáp USB)
          </summary>
          <div style="margin-top:10px;display:flex;gap:8px;">
            <input class="input" id="oppoIpPortInput" placeholder="Nhập IP:Port Gỡ lỗi không dây (vd: 192.168.1.95:41567)">
            <button class="btn btn-green" onclick="connectOppoByIp(this)">⚡ Nối IP:Port</button>
          </div>
          <div style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <input class="input" id="pairIpPortInput" placeholder="IP:Port Ghép nối (vd: 192.168.1.95:38123)">
            <input class="input" id="pairCodeInput" placeholder="Mã 6 số (vd: 652918)">
          </div>
          <button class="btn btn-gold" style="width:100%;margin-top:8px;" onclick="pairOppo(this)">🔗 Ghép Nối Bằng Mã 6 Số</button>
        </details>
      </div>

      <!-- HỘP PHẢI: BỘ NHẮC LỊCH 1 TIẾNG & LƯU NHÁP TỰ ĐỘNG -->
      <div class="card">
        <h3>
          <span>⏰ Bộ Tự Động Lưu Nháp & Nhắc Lịch (1 Tiếng / 1 Video)</span>
          <span id="schedBadge" style="font-size:11.5px;color:#4ade80;font-weight:700;">ĐANG BẬT</span>
        </h3>
        <div style="font-size:12.5px;color:var(--muted);margin-bottom:8px;">
          Mỗi 60 phút, hệ thống tự động đẩy bài kế tiếp vào mục <b>[Nháp]</b> trên Oppo A57 (kèm Caption Tiếng Việt có dấu) và bật chuông nhắc bạn gắn sản phẩm:
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;background:#090d16;border:1px solid #1e293b;border-radius:10px;padding:10px 14px;margin-bottom:10px;">
          <div>
            <div style="font-size:11.5px;color:var(--muted);">Thời gian đếm ngược tới bài tiếp theo:</div>
            <div id="countdownBox" style="font-size:22px;font-weight:900;color:var(--gold);">--:--</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-gold" onclick="triggerReminderNow(this)">
              📝 Lưu Nháp Bài Tiếp Theo Ngay
            </button>
            <button class="btn btn-dark" id="toggleSchedBtn" onclick="toggleScheduler(this)">
              ⏸ Tắt Tự Động 1H
            </button>
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#94a3b8;">
          <span>Kho Video Offline trên Laptop: <b id="offlineReadyTxt" style="color:#4ade80;">0</b> video</span>
          <button class="btn btn-blue" style="padding:6px 12px;font-size:12px;" onclick="syncR630(this)">
            ☁️ Đồng Bộ Kho Video R630 Ngay
          </button>
        </div>
      </div>
    </div>

    <!-- BẢNG DANH SÁCH VIDEO LÊN LỊCH -->
    <div class="card">
      <h3>
        <span>📅 Danh Sách Video Lên Lịch (1 Tiếng / 1 Video) — Đổi Sản Phẩm 1 Chạm & Tự Động Lưu Nháp</span>
        <span style="font-size:12px;color:var(--muted);font-weight:400;">
          Mẹo: Nếu thấy sản phẩm chưa đúng, chọn menu <b>"🔄 Đổi đúng Sản phẩm & Render lại bìa vàng"</b> ngay tại dòng đó!
        </span>
      </h3>
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th style="width:170px;">Khung Giờ & Kênh</th>
              <th style="width:270px;">Sản Phẩm & Đổi Nhanh Bìa Vàng</th>
              <th>Bìa Vàng Đã Đóng Lên Video & Caption Tiếng Việt Có Dấu</th>
              <th style="width:250px;">Thao Tác Chuẩn 2 Bước</th>
            </tr>
          </thead>
          <tbody id="queueBody">
            <tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px;">Đang tải danh sách video...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       TAB 2: ĐIỀU KHIỂN TỪ XA KHI ĐI DU LỊCH & TRẠM CÔNG TẮC BẬT / TẮT
       ===================================================================== -->
  <div class="tab-pane" id="tab2">
    <!-- BẢNG LINK ĐIỀU KHIỂN TỪ XA KHI ĐI DU LỊCH -->
    <div class="card" style="margin-bottom:16px;border:2px solid #38bdf8;">
      <h3>
        <span style="color:#38bdf8;">🌍 Bảng Link Truy Cập Từ Xa Khi Đi Du Lịch (Host Trực Tiếp Trên Chiếc Laptop Này)</span>
        <span id="laptopTunnelStatusBadge" style="font-size:12px;background:#166534;color:#4ade80;padding:4px 10px;border-radius:99px;">ĐANG HOẠT ĐỘNG</span>
      </h3>
      <div style="font-size:13px;color:#cbd5e1;margin-bottom:12px;line-height:1.5;">
        Khi bạn đi du lịch và để <b>chiếc Laptop này ở nhà</b> cắm nguồn + nối với <b>Oppo A57</b>, chiếc Laptop này sẽ tự chạy một đường hầm Cloudflare riêng biệt (<code>tiktok-laptop-master</code>). Bạn lấy <b>bất kỳ chiếc laptop hay điện thoại nào khác</b> mở các đường link dưới đây:
      </div>
      <div class="grid-2" style="margin-bottom:8px;">
        <div style="background:#090d16;border:1px solid #1e293b;border-radius:10px;padding:12px;">
          <div style="font-size:12px;color:var(--gold);font-weight:800;margin-bottom:4px;">
            1. ĐIỀU KHIỂN TRANG MASTER CỦA LAPTOP Ở NHÀ (TỪ LAPTOP KHÁC KHI ĐI DU LỊCH):
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px;">
            <code style="font-size:14px;color:#4ade80;font-weight:800;">https://master.phamvuong.io.vn</code>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" onclick="copyText('https://master.phamvuong.io.vn')">📋 Copy</button>
              <a class="btn btn-blue" style="padding:5px 10px;font-size:11.5px;" href="https://master.phamvuong.io.vn" target="_blank">↗ Mở</a>
            </div>
          </div>
          <div style="font-size:11.5px;color:var(--muted);margin-top:6px;">
            Giao diện y hệt trang này! Bấm Lưu Nháp từ xa ở Đà Lạt/Hà Nội là Oppo A57 ở nhà tự mở TikTok & Lưu Nháp ngay.
          </div>
        </div>

        <div style="background:#090d16;border:1px solid #1e293b;border-radius:10px;padding:12px;">
          <div style="font-size:12px;color:#f87171;font-weight:800;margin-bottom:4px;">
            2. CỨU HỘ PHẦN CỨNG iDRAC R620 (192.168.1.11 — KHÔNG QUA VM100, SERVER SẬP VẪN VÀO ĐƯỢC):
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px;">
            <code style="font-size:14px;color:#fde047;font-weight:800;">https://idrac.phamvuong.io.vn</code>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" onclick="copyText('https://idrac.phamvuong.io.vn')">📋 Copy</button>
              <a class="btn btn-gold" style="padding:5px 10px;font-size:11.5px;" href="https://idrac.phamvuong.io.vn" target="_blank">↗ Mở iDRAC</a>
            </div>
          </div>
          <div style="font-size:11.5px;color:var(--muted);margin-top:6px;">
            Link dự phòng số 2: <a href="https://idrac-rescue.phamvuong.io.vn" target="_blank" style="color:#38bdf8;">https://idrac-rescue.phamvuong.io.vn</a> · Đi thẳng từ <b>Laptop này -> 192.168.1.11</b>. Dù Server R620/R630 hay VM100 bị treo/tắt nguồn hoàn toàn, bạn vẫn vào được iDRAC để bấm Power On / Reboot Server!
          </div>
        </div>
      </div>

      <div class="grid-2" style="margin-bottom:0;">
        <div style="background:#090d16;border:1px solid #1e293b;border-radius:10px;padding:12px;">
          <div style="font-size:12px;color:#38bdf8;font-weight:800;margin-bottom:4px;">
            3. CỨU HỘ PROXMOX SERVER (192.168.1.20:8006 QUA LAPTOP — KHÔNG CẦN VM100):
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px;">
            <code style="font-size:13.5px;color:#38bdf8;font-weight:800;">https://pve-rescue.phamvuong.io.vn</code>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" onclick="copyText('https://pve-rescue.phamvuong.io.vn')">📋 Copy</button>
              <a class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" href="https://pve-rescue.phamvuong.io.vn" target="_blank">↗ Mở Proxmox</a>
            </div>
          </div>
        </div>

        <div style="background:#090d16;border:1px solid #1e293b;border-radius:10px;padding:12px;">
          <div style="font-size:12px;color:#a855f7;font-weight:800;margin-bottom:4px;">
            4. CỔNG KHO VIDEO SERVER R630 (CONTAINER 240 — 192.168.1.240:8088):
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px;">
            <code style="font-size:13.5px;color:#c084fc;font-weight:800;">https://tiktok.phamvuong.io.vn</code>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" onclick="copyText('https://tiktok.phamvuong.io.vn')">📋 Copy</button>
              <a class="btn btn-dark" style="padding:5px 10px;font-size:11.5px;" href="https://tiktok.phamvuong.io.vn" target="_blank">↗ Mở R630</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 5 CÔNG TẮC BẬT / TẮT THỦ CÔNG -->
    <div class="card">
      <h3>🎛️ Trạm Công Tắc Bật / Tắt Toàn Bộ Chương Trình (Bật Tắt Thủ Công 1 Chạm)</h3>
      <div class="grid-3">
        <!-- CÔNG TẮC 1 -->
        <div class="sw-card">
          <div>
            <div class="sw-head">
              <span class="sw-title">1. Tự Lưu Nháp 1 Tiếng/Video</span>
              <span class="sw-badge on" id="sw1_badge">ĐANG BẬT</span>
            </div>
            <div style="font-size:12px;color:var(--muted);margin-bottom:12px;">
              Chạy trên <b>Laptop này</b>: Tự động đẩy 1 video sang Oppo A57 + dán Tiếng Việt & bấm Nháp mỗi 60 phút.
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-green" style="flex:1;" onclick="setSchedulerState(true, this)">▶️ BẬT</button>
            <button class="btn btn-red" style="flex:1;" onclick="setSchedulerState(false, this)">⏹️ TẮT</button>
          </div>
        </div>

        <!-- CÔNG TẮC 2 -->
        <div class="sw-card">
          <div>
            <div class="sw-head">
              <span class="sw-title">2. Host Từ Xa Master & iDRAC</span>
              <span class="sw-badge on" id="sw2_badge">ĐANG BẬT</span>
            </div>
            <div style="font-size:12px;color:var(--muted);margin-bottom:12px;">
              Chạy trên <b>Laptop này</b>: Phát đường hầm <code>master.phamvuong.io.vn</code> & cứu hộ <code>idrac.phamvuong.io.vn</code> (192.168.1.11).
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-green" style="flex:1;" onclick="toggleLaptopTunnel(true, this)">▶️ BẬT HOST</button>
            <button class="btn btn-red" style="flex:1;" onclick="toggleLaptopTunnel(false, this)">⏹️ TẮT HOST</button>
          </div>
        </div>

        <!-- CÔNG TẮC 3 -->
        <div class="sw-card">
          <div>
            <div class="sw-head">
              <span class="sw-title">3. R630 Worker Tự Cắt Video</span>
              <span class="sw-badge on" id="sw3_badge">ĐANG BẬT</span>
            </div>
            <div style="font-size:12px;color:var(--muted);margin-bottom:12px;">
              Chạy trên <b>Server R630 (CT 240)</b>: Tự động theo dõi và cắt video mới, đóng bìa vàng 24/7.
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-green" style="flex:1;" onclick="ctrlR630('tiktok-worker','start', this)">▶️ BẬT</button>
            <button class="btn btn-red" style="flex:1;" onclick="ctrlR630('tiktok-worker','stop', this)">⏹️ TẮT</button>
            <button class="btn btn-dark" onclick="ctrlR630('tiktok-worker','restart', this)">🔄</button>
          </div>
        </div>
      </div>

      <div class="grid-2" style="margin-bottom:0;">
        <!-- CÔNG TẮC 4 -->
        <div class="sw-card">
          <div>
            <div class="sw-head">
              <span class="sw-title">4. Cổng Web R630 (tiktok.phamvuong.io.vn)</span>
              <span class="sw-badge on" id="sw4_badge">ĐANG BẬT</span>
            </div>
            <div style="font-size:12px;color:var(--muted);margin-bottom:12px;">
              Cổng API & Kho Video trên Server R630 phục vụ tải video về Laptop.
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-blue" style="flex:1;" onclick="ctrlR630('tiktok-portal','restart', this)">🔄 Khởi Động Lại Portal R630</button>
            <button class="btn btn-dark" style="flex:1;" onclick="ctrlR630('cloudflared-tiktok','restart', this)">☁️ Reset Tunnel R630</button>
          </div>
        </div>

        <!-- CÔNG TẮC 5 -->
        <div class="sw-card">
          <div>
            <div class="sw-head">
              <span class="sw-title">5. ADB Oppo A57 & Tắt Toàn Bộ Trạm Laptop</span>
              <span class="sw-badge on">CHỦ ĐỘNG</span>
            </div>
            <div style="font-size:12px;color:var(--muted);margin-bottom:12px;">
              Reset kết nối ADB khi điện thoại bị đơ, hoặc tắt hẳn mọi tiến trình trên Laptop này.
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-gold" style="flex:1;" onclick="ctrlLocal('restart_adb', this)">🔄 Reset ADB Oppo A57</button>
            <button class="btn btn-red" style="flex:1;" onclick="ctrlLocal('stop_hub', this)">🛑 TẮT HẲN TRẠM LAPTOP</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       TAB 3: THU & EDIT LINK LIVEVAULT MỚI + THÊM SẢN PHẨM MỚI
       ===================================================================== -->
  <div class="tab-pane" id="tab3">
    <div class="grid-2">
      <div class="card">
        <h3>🎬 Thu & Edit Loạt Video Mới Từ Link LiveVault Bác Chường</h3>
        <div style="font-size:12.5px;color:var(--muted);margin-bottom:12px;line-height:1.5;">
          Dán link LiveVault mới vào bên dưới. Hệ thống sẽ tải các clip highlight, dùng AI nhận diện giọng nói (hoặc gắn cứng sản phẩm bạn chọn), đóng khung bìa nền vàng chữ đen che chữ đỏ LiveVault và tạo 2 bản Unique hóa cho 2 kênh:
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#cbd5e1;font-weight:700;display:block;margin-bottom:4px;">1. Dán Link LiveVault Mới:</label>
          <input class="input" id="lvUrlInput" placeholder="https://livevault.work/...">
        </div>
        <div class="grid-2" style="margin-bottom:12px;">
          <div>
            <label style="font-size:12px;color:#cbd5e1;font-weight:700;display:block;margin-bottom:4px;">2. Số lượng clip muốn cắt:</label>
            <select class="input" id="lvMaxClips">
              <option value="3">Cắt nhanh 3 clip đầu (Test)</option>
              <option value="5" selected>Cắt 5 clip (Tạo 10 video cho 2 kênh)</option>
              <option value="10">Cắt 10 clip (Tạo 20 video cho 2 kênh)</option>
              <option value="25">Cắt toàn bộ 25 clip (Tạo 50 video)</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;color:#cbd5e1;font-weight:700;display:block;margin-bottom:4px;">3. Sản phẩm áp dụng:</label>
            <select class="input" id="lvProductKey">
              <option value="AUTO" selected>🤖 Tự động nhận diện theo giọng nói (8 sản phẩm)</option>
              <option value="marial_gel">Hỗn dịch dạ dày & trào ngược Marial Gel Ý (Bao tử)</option>
              <option value="ginkgo_bonao">Viên uống dưỡng não Ginkgo Biloba Mỹ (Tiền đình)</option>
              <option value="canxi_mason">Canxi hữu cơ Mỹ Mason Natural (Tê tay, chuột rút)</option>
              <option value="bokhop_chondro">Viên uống bổ khớp Chondro-Aid Pháp (Đau khớp gối)</option>
              <option value="omega3_arko">Dầu cá Omega 3 Arkopharma Pháp (Mỡ máu, khô mắt)</option>
              <option value="vitamin_azinc">Vitamin tổng hợp Azinc 3B Pháp (Mệt mỏi, thần kinh tọa)</option>
              <option value="collagen_chalpha">Collagen sụn khớp CH-Alpha Plus Đức (Dạng ống)</option>
              <option value="biotin_forcapil">Viên uống dưỡng tóc Biotin Forcapil Pháp (Rụng tóc)</option>
            </select>
          </div>
        </div>
        <button class="btn btn-green" style="width:100%;padding:13px;font-size:14px;" onclick="startBatchEdit(this)">
          🎬 Bắt Đầu Thu & Edit Loạt Video Mới Ngay
        </button>

        <div style="margin-top:12px;background:#090d16;border:1px solid #1e293b;border-radius:10px;padding:10px 12px;">
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px;">
            <span id="editorStepBox" style="color:#fde047;font-weight:700;">Sẵn sàng nhận link LiveVault mới.</span>
            <span id="editorPctBox" style="color:#4ade80;font-weight:800;">0%</span>
          </div>
          <div style="width:100%;height:8px;background:#1e293b;border-radius:99px;overflow:hidden;">
            <div id="editorBar" style="width:0%;height:100%;background:linear-gradient(90deg,#facc15,#22c55e);transition:width 0.3s;"></div>
          </div>
        </div>
      </div>

      <!-- HỘP THÊM SẢN PHẨM MỚI -->
      <div class="card">
        <h3>➕ Thêm Sản Phẩm Mới Vào Từ Điển Nhận Diện & Đóng Bìa Vàng</h3>
        <div style="font-size:12.5px;color:var(--muted);margin-bottom:10px;">
          Nếu Bác Chường lên sóng một sản phẩm hoàn toàn mới, bạn điền thông tin dưới đây để hệ thống tự động nhận diện giọng nói và đóng bìa vàng đúng chuẩn:
        </div>
        <div class="grid-2" style="margin-bottom:8px;">
          <input class="input" id="cpKey" placeholder="Mã viết tắt (vd: men_visinh)">
          <input class="input" id="cpName" placeholder="Tên đầy đủ (vd: Men vi sinh đường ruột Pháp)">
        </div>
        <div class="grid-2" style="margin-bottom:8px;">
          <input class="input" id="cpTitle" placeholder="Dòng 1 bìa vàng (vd: Men Vi Sinh Đường Ruột)">
          <input class="input" id="cpBen1" placeholder="Dòng 2 công dụng (vd: Hỗ trợ tiêu hóa, giảm đầy bụng)">
        </div>
        <div class="grid-2" style="margin-bottom:8px;">
          <input class="input" id="cpBen2" placeholder="Dòng 3 triệu chứng (vd: Ăn không tiêu, rối loạn đại tràng)">
          <input class="input" id="cpDosage" placeholder="Dòng 4 liều dùng (vd: Ngày 1-2 gói sau ăn)">
        </div>
        <input class="input" id="cpKeywords" placeholder="Các từ khóa Bác Chường hay nói, cách nhau dấu phẩy (vd: đại tràng, men vi sinh, tiêu hóa)" style="margin-bottom:10px;">
        <button class="btn btn-gold" style="width:100%;" onclick="addCustomProductUI(this)">
          ➕ Lưu Sản Phẩm Mới Vào Hệ Thống
        </button>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       TAB 4: SỔ CÁI CHỐNG ĐĂNG TRÙNG SHA-256 & NHẬT KÝ HỆ THỐNG
       ===================================================================== -->
  <div class="tab-pane" id="tab4">
    <div class="grid-2">
      <div class="card">
        <h3>📜 Nhật Ký Thực Thi Thời Gian Thực (Live System Console)</h3>
        <div id="fullLogConsole" style="background:#050811;border:1px solid #1e293b;border-radius:10px;padding:12px;font-family:Consolas,monospace;font-size:12px;color:#4ade80;height:260px;overflow-y:auto;line-height:1.55;">
        </div>
      </div>
      <div class="card">
        <h3>🗺️ Mô Hình Hoạt Động Khi Ở Nhà & Khi Đi Du Lịch</h3>
        <div style="font-size:12.5px;color:#cbd5e1;line-height:1.6;">
          <div style="background:#090d16;border-left:4px solid var(--gold);padding:8px 12px;border-radius:6px;margin-bottom:8px;">
            <b style="color:var(--gold);">1. Chiếc Laptop này (Để ở nhà khi đi du lịch):</b><br>
            • Cắm nguồn 24/7 + cắm cáp USB nối với điện thoại <b>Oppo A57</b>.<br>
            • Chạy <code>Start-TikTok-AutoHub.cmd</code>: Vừa điều khiển Oppo A57 tự Lưu Nháp, vừa phát đường hầm độc lập <code>https://master.phamvuong.io.vn</code> và đường hầm cứu hộ phần cứng iDRAC <code>https://idrac.phamvuong.io.vn</code> (trỏ thẳng vào <code>192.168.1.11</code>).
          </div>
          <div style="background:#090d16;border-left:4px solid #38bdf8;padding:8px 12px;border-radius:6px;margin-bottom:8px;">
            <b style="color:#38bdf8;">2. Laptop / Điện thoại mang theo khi đi du lịch:</b><br>
            • Mở trình duyệt vào <code>https://master.phamvuong.io.vn</code> để xem lịch, đổi sản phẩm, bấm Lưu Nháp từ xa.<br>
            • Nếu Server R620/R630 ở nhà bị cúp điện hay treo, mở <code>https://idrac.phamvuong.io.vn</code> (nhờ Laptop ở nhà vẫn sống) để vào thẳng iDRAC <code>192.168.1.11</code> bật lại nguồn Server!
          </div>
          <div style="background:#090d16;border-left:4px solid #22c55e;padding:8px 12px;border-radius:6px;">
            <b style="color:#22c55e;">3. Khi nào cần bật Antigravity?</b><br>
            • <b>KHÔNG CẦN bật Antigravity</b> khi chạy hàng ngày hay khi đi du lịch! Bạn chỉ mở Antigravity khi muốn viết thêm tính năng mới.
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>🛡️ Sổ Cái Chống Đăng Trùng 3 Lớp (Các Video Đã Đăng Từ Nháp — Khóa Cứng Mã Băm SHA-256)</h3>
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>Thời Gian Đăng</th>
              <th>Tài Khoản</th>
              <th>Mã Clip Gốc</th>
              <th>Sản Phẩm</th>
              <th>Mã Băm Video (SHA-256)</th>
              <th>Trạng Thái</th>
            </tr>
          </thead>
          <tbody id="ledgerBody"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>
const PRODUCT_OPTIONS = [
  {key: "marial_gel", label: "Hỗn dịch dạ dày & trào ngược Marial Gel Ý (Bao tử)"},
  {key: "ginkgo_bonao", label: "Viên uống dưỡng não Ginkgo Biloba Mỹ (Tiền đình)"},
  {key: "canxi_mason", label: "Canxi hữu cơ Mỹ Mason Natural (Tê tay chân, chuột rút)"},
  {key: "bokhop_chondro", label: "Viên uống bổ khớp Chondro-Aid Pháp (Khô khớp, đau gối)"},
  {key: "omega3_arko", label: "Dầu cá Omega 3 Arkopharma Pháp (Mỡ máu, khô mắt)"},
  {key: "vitamin_azinc", label: "Vitamin tổng hợp Azinc 3B Pháp (Mệt mỏi, thần kinh tọa)"},
  {key: "collagen_chalpha", label: "Collagen sụn khớp CH-Alpha Plus Đức (Dạng ống)"},
  {key: "biotin_forcapil", label: "Viên uống dưỡng tóc Biotin Forcapil Pháp (Rụng tóc)"}
];

let LAST_STATE = null;
let ACTIVE_ACTION_TIMER = null;
let ACTION_START_EPOCH = 0;

function switchTab(tabId) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  const pane = document.getElementById(tabId);
  const btn = document.getElementById('btn_' + tabId);
  if (pane) pane.classList.add('active');
  if (btn) btn.classList.add('active');
}

function showToast(msg, isError = false) {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast' + (isError ? ' error' : '');
  t.innerHTML = `<div style="font-weight:800;margin-bottom:3px;color:${isError ? '#f87171' : '#4ade80'};">
    ${isError ? '⚠️ THÔNG BÁO / LƯU Ý' : '✅ THAO TÁC HOÀN TẤT'}
  </div><div>${msg}</div>`;
  c.appendChild(t);
  setTimeout(() => { t.remove(); }, 7500);
}

function copyText(txt) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(txt);
  }
  showToast("📋 Đã copy vào bộ nhớ tạm: " + txt, false);
}

function showLiveOverlay(title, stepText) {
  const ov = document.getElementById('liveOverlay');
  document.getElementById('liveTitle').textContent = title;
  document.getElementById('liveStep').textContent = stepText;
  ov.classList.add('show');
  ACTION_START_EPOCH = Date.now();
  if (ACTIVE_ACTION_TIMER) clearInterval(ACTIVE_ACTION_TIMER);
  ACTIVE_ACTION_TIMER = setInterval(async () => {
    const sec = Math.floor((Date.now() - ACTION_START_EPOCH) / 1000);
    document.getElementById('liveTimer').textContent = sec;
    try {
      const r = await fetch('/api/live_progress');
      const p = await r.json();
      if (p.step) document.getElementById('liveStep').textContent = p.step;
      if (p.logs && p.logs.length) {
        const box = document.getElementById('liveConsole');
        box.innerHTML = p.logs.map(l => `<div>${l}</div>`).join('');
        box.scrollTop = box.scrollHeight;
      }
    } catch (e) {}
  }, 850);
}

function hideLiveOverlay() {
  if (ACTIVE_ACTION_TIMER) {
    clearInterval(ACTIVE_ACTION_TIMER);
    ACTIVE_ACTION_TIMER = null;
  }
  document.getElementById('liveOverlay').classList.remove('show');
}

async function runAction(title, stepHint, url, payload = {}, btnEl = null) {
  let oldHtml = null;
  if (btnEl) {
    oldHtml = btnEl.innerHTML;
    btnEl.disabled = true;
    btnEl.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span> Đang xử lý...`;
  }
  showLiveOverlay(title, stepHint);
  document.getElementById('lastActionText').textContent = `⏳ ${title}: ${stepHint}`;
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    hideLiveOverlay();
    const msg = d.message || d.detail || d.last_bridge_msg || "Đã thực thi xong.";
    const isErr = (d.ok === false) || (d.connected === false && url === '/api/connect_oppo');
    showToast(msg, isErr);
    await loadStatus();
    return d;
  } catch (err) {
    hideLiveOverlay();
    showToast("Không thể kết nối tới máy chủ Master: " + err, true);
    return {ok: false};
  } finally {
    if (btnEl && oldHtml !== null) {
      btnEl.disabled = false;
      btnEl.innerHTML = oldHtml;
    }
  }
}

function fmtSec(s) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m} phút ${sec < 10 ? '0' : ''}${sec} giây`;
}

function updateSmartFlowAndStepper(d) {
  const oppoOk = d.runtime.oppo_status && d.runtime.oppo_status.connected;
  const q = d.ready_queue || [];
  const cachedCount = d.runtime.r630_sync_status.cached_offline_ready || 0;
  const firstItem = q.length > 0 ? q[0] : null;
  const hasDraft = q.some(x => x.status === 'SAVED_DRAFT');
  const draftItem = q.find(x => x.status === 'SAVED_DRAFT');

  // Step 1: Oppo A57
  const s1 = document.getElementById('stepCard1');
  const n1 = document.getElementById('stepNum1');
  s1.className = 'step-card ' + (oppoOk ? 'done' : 'active');
  n1.textContent = oppoOk ? '✓ Bước 1: Hoàn tất' : '👉 Bước 1: Cần làm ngay';
  document.getElementById('stepDesc1').textContent = oppoOk
    ? `Đã kết nối Oppo A57 (${d.runtime.oppo_status.serial} · ${d.runtime.oppo_status.mode}).`
    : `Oppo A57 chưa kết nối. Cắm cáp USB hoặc bật Wi-Fi ADB rồi bấm Kết nối.`;

  // Step 2: Kho Video
  const s2 = document.getElementById('stepCard2');
  const n2 = document.getElementById('stepNum2');
  const videoOk = cachedCount > 0;
  s2.className = 'step-card ' + (videoOk ? 'done' : (oppoOk ? 'active' : ''));
  n2.textContent = videoOk ? `✓ Bước 2: Sẵn sàng (${cachedCount} bài)` : 'Bước 2';
  if (firstItem) {
    document.getElementById('stepDesc2').textContent = `Bài kế tiếp: ${firstItem.channel} — ${firstItem.product_name.split(' (Tự cắt')[0]}`;
  }

  // Step 3: Lưu Nháp
  const s3 = document.getElementById('stepCard3');
  const n3 = document.getElementById('stepNum3');
  if (hasDraft) {
    s3.className = 'step-card done';
    n3.textContent = '✓ Bước 3: Đã Lưu Nháp';
  } else if (oppoOk && videoOk) {
    s3.className = 'step-card active';
    n3.textContent = '👉 Bước 3: Sẵn sàng chạy';
  } else {
    s3.className = 'step-card';
    n3.textContent = 'Bước 3';
  }

  // Step 4: Mở Nháp & Đánh dấu đã đăng
  const s4 = document.getElementById('stepCard4');
  const n4 = document.getElementById('stepNum4');
  if (hasDraft) {
    s4.className = 'step-card active';
    n4.textContent = '👉 Bước 4: Cần xác nhận đăng';
  } else {
    s4.className = 'step-card';
    n4.textContent = 'Bước 4';
  }

  // SMART COACH RECOMMENDATION
  const coachTxt = document.getElementById('coachText');
  const coachBtn = document.getElementById('coachActionBtnWrap');
  if (!oppoOk) {
    coachTxt.innerHTML = `💡 <b>GỢI Ý BƯỚC TIẾP THEO:</b> Điện thoại <b>Oppo A57</b> chưa kết nối với Laptop. Hãy cắm cáp USB (hoặc bật Gỡ lỗi không dây) rồi bấm nút bên phải:`;
    coachBtn.innerHTML = `<button class="btn btn-gold" onclick="connectOppo(this)">🔌 Tự Động Tìm & Nối Oppo A57 Ngay</button>`;
  } else if (hasDraft && draftItem) {
    coachTxt.innerHTML = `💡 <b>GỢI Ý BƯỚC TIẾP THEO:</b> Video <b>${draftItem.product_name.split(' (Tự cắt')[0]}</b> đã nằm sẵn trong mục <b>[Nháp]</b> của kênh <b>${draftItem.channel}</b> trên Oppo A57! Hãy mở điện thoại gắn sản phẩm GMV Max & bấm <b>[Đăng]</b>, sau đó bấm nút xác nhận:`;
    coachBtn.innerHTML = `<button class="btn btn-green" onclick="markPosted('${draftItem.id}', this)">✅ Xác Nhận Đã Đăng Bài ${draftItem.channel}</button>`;
  } else if (firstItem) {
    coachTxt.innerHTML = `💡 <b>GỢI Ý BƯỚC TIẾP THEO:</b> Mọi kết nối đã sẵn sàng! Bài tiếp theo là kênh <b>${firstItem.channel}</b> — Sản phẩm: <b>${firstItem.product_name.split(' (Tự cắt')[0]}</b>. Bấm nút bên phải để tự động đẩy video sang Oppo A57, dán Tiếng Việt & Lưu Nháp:`;
    coachBtn.innerHTML = `<button class="btn btn-gold" onclick="saveDraftOnOppo('${firstItem.id}','${firstItem.channel}', this)">📝 Đẩy Video #1 + Dán Tiếng Việt & Lưu Nháp Ngay</button>`;
  } else {
    coachTxt.innerHTML = `💡 <b>GỢI Ý BƯỚC TIẾP THEO:</b> Hàng chờ hiện tại đã đăng hết. Hãy bấm sang Tab 3 để thu & edit link LiveVault mới hoặc đồng bộ từ R630:`;
    coachBtn.innerHTML = `<button class="btn btn-blue" onclick="syncR630(this)">☁️ Đồng Bộ Kho Video R630</button>`;
  }
}

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    LAST_STATE = d;

    document.getElementById('lastActionText').textContent = d.runtime.last_action_result || 'Sẵn sàng.';
    document.getElementById('lastActionTime').textContent = 'Cập nhật lúc ' + (d.runtime.last_action_time || '');

    // Live console in Tab 4
    if (d.live_action && d.live_action.logs) {
      const fc = document.getElementById('fullLogConsole');
      fc.innerHTML = d.live_action.logs.map(l => `<div>${l}</div>`).join('');
      fc.scrollTop = fc.scrollHeight;
    }

    // Header pills
    const oppo = d.runtime.oppo_status || {};
    const pOppo = document.getElementById('pillOppo');
    if (oppo.connected) {
      pOppo.className = 'pill ok';
      pOppo.textContent = `📱 Oppo A57: ĐÃ KẾT NỐI (${oppo.mode})`;
      document.getElementById('oppoModeBadge').textContent = `✓ ${oppo.serial}`;
    } else {
      pOppo.className = 'pill err';
      pOppo.textContent = `📱 Oppo A57: CHƯA KẾT NỐI`;
      document.getElementById('oppoModeBadge').textContent = `Chưa kết nối`;
    }
    document.getElementById('oppoDetailBox').textContent = oppo.detail || '';

    const pMaster = document.getElementById('pillRemoteMaster');
    const ltActive = d.runtime.laptop_tunnel_active;
    pMaster.className = 'pill ' + (ltActive ? 'ok' : 'warn');
    pMaster.textContent = ltActive ? '🌍 Master Từ Xa: master.phamvuong.io.vn (ONLINE)' : '🌍 Master Từ Xa: Đang Tắt';

    const pIdrac = document.getElementById('pillIdrac');
    pIdrac.className = 'pill ' + ((ltActive && d.idrac_lan_ok) ? 'ok' : 'warn');
    pIdrac.textContent = (ltActive && d.idrac_lan_ok)
      ? '🛡️ Cứu Hộ iDRAC (192.168.1.11): ONLINE QUA LAPTOP'
      : '🛡️ iDRAC 192.168.1.11: ' + (d.idrac_lan_ok ? 'LAN OK (Tunnel tắt)' : 'Kiểm tra LAN');

    const sync = d.runtime.r630_sync_status || {};
    document.getElementById('pillCache').textContent = `📦 Kho Video: ${sync.cached_offline_ready || 0}/${sync.total_queue || 0} bài`;
    document.getElementById('offlineReadyTxt').textContent = `${sync.cached_offline_ready || 0}/${sync.total_queue || 0}`;
    document.getElementById('badgeQueueCount').textContent = (d.ready_queue || []).length;

    // Scheduler countdown
    const schedOn = d.settings.auto_scheduler_enabled;
    document.getElementById('schedBadge').textContent = schedOn ? '✓ ĐANG BẬT TỰ ĐỘNG 1H' : '⏸ ĐANG TẠM DỪNG';
    document.getElementById('schedBadge').style.color = schedOn ? '#4ade80' : '#facc15';
    document.getElementById('countdownBox').textContent = schedOn ? fmtSec(d.next_wait_seconds) : 'Đang tạm dừng';
    const tBtn = document.getElementById('toggleSchedBtn');
    tBtn.textContent = schedOn ? '⏸ Tắt Tự Động 1H' : '▶️ Bật Tự Động 1H';
    tBtn.dataset.enabled = schedOn ? '1' : '0';

    // Tab 2 Switches
    const sw1 = document.getElementById('sw1_badge');
    sw1.className = 'sw-badge ' + (schedOn ? 'on' : 'off');
    sw1.textContent = schedOn ? 'ĐANG BẬT' : 'ĐANG TẮT';

    const sw2 = document.getElementById('sw2_badge');
    sw2.className = 'sw-badge ' + (ltActive ? 'on' : 'off');
    sw2.textContent = ltActive ? 'ĐANG BẬT' : 'ĐANG TẮT';
    const ltBadge = document.getElementById('laptopTunnelStatusBadge');
    ltBadge.textContent = ltActive ? '✓ ĐƯỜNG HẦM LAPTOP ĐANG BẬT' : '⏹️ ĐƯỜNG HẦM LAPTOP ĐANG TẮT';
    ltBadge.style.background = ltActive ? '#166534' : '#7f1d1d';

    if (d.r630_services) {
      const wOn = d.r630_services['tiktok-worker'];
      const pOn = d.r630_services['tiktok-portal'];
      const sw3 = document.getElementById('sw3_badge');
      sw3.className = 'sw-badge ' + (wOn ? 'on' : 'off');
      sw3.textContent = wOn ? 'ĐANG BẬT' : 'ĐANG TẮT';
      const sw4 = document.getElementById('sw4_badge');
      sw4.className = 'sw-badge ' + (pOn ? 'on' : 'off');
      sw4.textContent = pOn ? 'ĐANG BẬT' : 'ĐANG TẮT';
    }

    // Tab 1 & Tab 3 Editor progress
    if (d.editor) {
      const stepTxt = d.editor.current_step || d.editor.progress_text || 'Sẵn sàng';
      const pctVal = (d.editor.progress_pct || 0);
      document.getElementById('editorStepBox').textContent = stepTxt;
      document.getElementById('editorPctBox').textContent = pctVal + '%';
      document.getElementById('editorBar').style.width = pctVal + '%';

      const qs = document.getElementById('quickEditorStep');
      const qp = document.getElementById('quickEditorPctNum');
      const qb = document.getElementById('quickEditorBar');
      const qBadge = document.getElementById('quickEditorPct');
      if (qs) qs.textContent = stepTxt;
      if (qp) qp.textContent = pctVal + '%';
      if (qb) qb.style.width = pctVal + '%';
      if (qBadge) {
        qBadge.textContent = d.editor.is_running ? `⏳ ĐANG CHẠY (${pctVal}%)` : '✓ SẴN SÀNG';
        qBadge.style.background = d.editor.is_running ? '#854d0e' : '#166534';
      }
    }

    // Update Smart Flow & Stepper
    updateSmartFlowAndStepper(d);

    // Render Queue Table
    const qb = document.getElementById('queueBody');
    qb.innerHTML = '';
    (d.ready_queue || []).forEach((item, idx) => {
      const isCh1 = item.channel === '@suckhoeviet.2';
      const isDraft = item.status === 'SAVED_DRAFT';
      const fname = (item.output_video || '').split('/').pop();
      const optsHtml = PRODUCT_OPTIONS.map(o =>
        `<option value="${o.key}" ${item.product_key === o.key ? 'selected' : ''}>${o.label}</option>`
      ).join('');

      const tr = document.createElement('tr');
      if (idx === 0) tr.style.background = 'rgba(250,204,21,0.05)';
      tr.innerHTML = `
        <td>
          <div style="font-weight:800;color:${idx===0 ? '#fde047' : '#e2e8f0'};margin-bottom:5px;">
            ${idx===0 ? '👉 ' : ''}${item.scheduled_1h_slot}
          </div>
          <span class="${isCh1 ? 'tag-ch1' : 'tag-ch2'}">${item.channel}</span>
          ${isDraft ? `<div class="draft-badge">✓ ĐÃ LƯU NHÁP TRÊN OPPO (${item.drafted_at || ''})</div>` : ''}
          <div style="margin-top:6px;font-size:11.5px;color:${item.cached_offline ? '#4ade80' : '#f87171'};">
            ${item.cached_offline ? '✓ Đã tải sẵn Offline trên Laptop' : '⏳ Chưa tải cache'}
          </div>
        </td>
        <td>
          <div style="font-weight:800;color:#fde047;font-size:13.5px;line-height:1.35;">${item.product_name}</div>
          <div style="font-size:11.5px;color:#4ade80;margin-top:4px;">🛒 ${item.seller_name || 'Shop GMV Max (isAd: TRUE)'}</div>
          <div style="margin-top:8px;background:#090d16;border:1px solid #334155;border-radius:8px;padding:6px 8px;">
            <div style="font-size:11px;color:#38bdf8;font-weight:700;margin-bottom:4px;">🔄 Đổi sản phẩm & Vẽ lại bìa vàng:</div>
            <select class="input" style="padding:5px 8px;font-size:11.5px;" onchange="changeItemProduct('${item.id}', this.value, this)">
              ${optsHtml}
            </select>
          </div>
        </td>
        <td>
          ${item.cover_text ? `<div class="cover-pill-preview">${item.cover_text}</div>` : ''}
          <div class="cap-preview">${item.caption_seo}</div>
          ${item.transcript ? `<details style="margin-top:6px;font-size:11.5px;color:#94a3b8;"><summary style="cursor:pointer;color:#38bdf8;">🎙️ Xem lời thoại AI nghe được từ video gốc</summary><div style="padding:6px;background:#050811;border-radius:6px;margin-top:4px;">${item.transcript}</div></details>` : ''}
        </td>
        <td>
          <div style="display:flex;flex-direction:column;gap:8px;">
            <button class="btn btn-gold" onclick="saveDraftOnOppo('${item.id}','${item.channel}', this)">
              📝 1. Đẩy Video + Dán Tiếng Việt & Lưu Nháp
            </button>
            <button class="btn btn-green" onclick="markPosted('${item.id}', this)">
              ✅ 2. Đánh Dấu Đã Đăng Từ Nháp
            </button>
            <div style="display:flex;gap:6px;">
              <a class="btn btn-dark" style="flex:1;padding:6px;font-size:11.5px;" href="/video?file=${encodeURIComponent(fname)}" target="_blank">
                👁️ Xem Thử Video
              </a>
              <button class="btn btn-dark" style="flex:1;padding:6px;font-size:11.5px;" onclick="copyText(${JSON.stringify(item.caption_seo)})">
                📋 Copy Caption
              </button>
            </div>
          </div>
        </td>
      `;
      qb.appendChild(tr);
    });

    // Render Ledger
    const lb = document.getElementById('ledgerBody');
    lb.innerHTML = '';
    if (!d.ledger || d.ledger.length === 0) {
      lb.innerHTML = '<tr><td colspan="6" style="color:#64748b;text-align:center;padding:18px;">Chưa có video nào trong Sổ cái đã đăng.</td></tr>';
    } else {
      d.ledger.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.posted_at}</td>
          <td><span class="${row.channel==='@suckhoeviet.2' ? 'tag-ch1' : 'tag-ch2'}">${row.channel}</span></td>
          <td><code>${row.clip_id}</code></td>
          <td>${row.product_name}</td>
          <td><code>${row.file_sha256}</code></td>
          <td><span style="color:#4ade80;font-weight:700;">🔒 ĐÃ KHÓA CHỐNG TRÙNG (${row.post_mode})</span></td>
        `;
        lb.appendChild(tr);
      });
    }
  } catch (e) {}
}

function connectOppo(btn) {
  runAction("Kết nối Điện thoại Oppo A57", "Đang tự động tìm Oppo A57 qua cáp USB, mDNS và quét mạng LAN...", "/api/connect_oppo", {}, btn);
}
function connectOppoByIp(btn) {
  const val = document.getElementById('oppoIpPortInput').value.trim();
  if (!val) { showToast("Vui lòng nhập IP:Port trên màn hình Gỡ lỗi không dây của Oppo A57!", true); return; }
  runAction("Kết nối Oppo A57 qua IP:Port", `Đang kết nối tới ${val}...`, "/api/connect_oppo", {ip_port: val}, btn);
}
function pairOppo(btn) {
  const pIp = document.getElementById('pairIpPortInput').value.trim();
  const pCode = document.getElementById('pairCodeInput').value.trim();
  const mIp = document.getElementById('oppoIpPortInput').value.trim();
  if (!pIp || !pCode) { showToast("Vui lòng nhập đủ IP:Port ghép nối và Mã 6 số!", true); return; }
  runAction("Ghép nối Oppo A57 bằng Mã 6 Số", `Đang ghép nối với ${pIp} (Mã: ${pCode})...`, "/api/pair_oppo", {pair_ip_port: pIp, pair_code: pCode, main_ip_port: mIp}, btn);
}
function syncR630(btn) {
  runAction("Đồng bộ Kho Video từ Server R630", "Đang tải danh sách video mới và lưu vào bộ nhớ đệm Offline trên Laptop...", "/api/sync_r630", {}, btn);
}
function testSwitch(ch, btn) {
  runAction(`Chuyển tài khoản TikTok sang ${ch}`, `Đang mở TikTok trên Oppo A57 và chuyển sang ${ch}...`, "/api/test_switch", {channel: ch}, btn);
}
function saveDraftOnOppo(id, ch, btn) {
  runAction(
    `Đẩy Video + Dán Tiếng Việt & Lưu Nháp (${ch})`,
    `Đang chuyển kênh ${ch} -> Đẩy 1 video vào Camera -> Dán Caption Tiếng Việt có dấu -> Bấm Lưu Nháp (Mất khoảng 20-30 giây)...`,
    "/api/save_draft_on_oppo",
    {item_id: id, channel: ch},
    btn
  );
}
function markPosted(id, btn) {
  runAction("Xác nhận Đã Đăng & Khóa Chống Trùng SHA-256", "Đang ghi khóa mã băm SHA-256 vào Sổ cái và xóa video tạm đã đăng...", "/api/mark_posted", {item_id: id}, btn);
}
function triggerReminderNow(btn) {
  runAction("Lưu Nháp & Nhắc Đăng Bài Tiếp Theo", "Đang tự động Lưu Nháp bài đầu tiên lên Oppo A57 và bật chuông nhắc...", "/api/trigger_reminder_now", {}, btn);
}
function toggleScheduler(btn) {
  const cur = btn.dataset.enabled === '1';
  setSchedulerState(!cur, btn);
}
function setSchedulerState(enable, btn) {
  runAction(
    enable ? "Bật Tự động Lưu Nháp 1 Tiếng/Video" : "Tắt Tự động Lưu Nháp 1 Tiếng/Video",
    "Đang cập nhật cấu hình bộ đếm ngược...",
    "/api/toggle_scheduler",
    {enabled: enable},
    btn
  );
}
function toggleLaptopTunnel(enable, btn) {
  runAction(
    enable ? "Bật Host Từ Xa Master & Cứu Hộ iDRAC (192.168.1.11)" : "Tắt Host Từ Xa Trên Laptop",
    enable ? "Đang khởi chạy đường hầm Cloudflare tiktok-laptop-master trực tiếp trên Laptop..." : "Đang dừng đường hầm Cloudflare trên Laptop...",
    "/api/toggle_laptop_tunnel",
    {enable: enable},
    btn
  );
}
function ctrlR630(service, action, btn) {
  runAction(
    `Điều khiển Server R630 (${service} -> ${action.toUpperCase()})`,
    `Đang gửi lệnh ${action} tới dịch vụ ${service} trên Server R630...`,
    "/api/r630_service_control",
    {service: service, action: action},
    btn
  );
}
function ctrlLocal(action, btn) {
  if (action === 'stop_hub' && !confirm('Bạn có chắc muốn TẮT HẲN Trạm Kiểm Soát trên Laptop và Đường hầm Cloudflare không?')) return;
  runAction(
    action === 'restart_adb' ? "Reset kết nối ADB Oppo A57" : "Tắt toàn bộ Trạm Kiểm Soát Laptop",
    "Đang thực thi lệnh hệ thống trên Laptop...",
    "/api/local_service_control",
    {action: action},
    btn
  );
}
function changeItemProduct(itemId, newProductKey, selectEl) {
  runAction(
    `Đổi sản phẩm sang "${newProductKey}" & Render lại bìa vàng`,
    `Đang dùng FFmpeg vẽ lại hộp bìa vàng mới trên file .mp4 và cập nhật Caption Tiếng Việt chuẩn SEO...`,
    "/api/change_item_product",
    {item_id: itemId, product_key: newProductKey},
    null
  );
}
function startQuickBatchEdit(useLatestLocal, btn) {
  let url = document.getElementById('quickLvUrlInput').value.trim();
  if (useLatestLocal || !url) {
    url = 'AUTO';
  }
  const maxC = document.getElementById('quickLvMaxClips').value;
  const pKey = document.getElementById('quickLvProductKey').value;
  runAction(
    `Chạy Tự Động Toàn Trình (${maxC} Clip -> Cắt Bìa Vàng -> Lên Lịch -> Đẩy Lưu Nháp Oppo A57)`,
    "Đang lấy clip, nhận diện giọng nói 8 sản phẩm, đóng bìa vàng 2 kênh và tự đẩy bài đầu tiên sang Oppo A57...",
    "/api/fetch_edit_new_link",
    {livevault_url: url, max_clips: maxC, product_key: pKey},
    btn
  );
}
function startBatchEdit(btn) {
  const url = document.getElementById('lvUrlInput').value.trim() || 'AUTO';
  const maxC = document.getElementById('lvMaxClips').value;
  const pKey = document.getElementById('lvProductKey').value;
  runAction(
    `Thu & Edit ${maxC} Clip từ LiveVault`,
    "Đang khởi chạy tiến trình tải clip, nhận diện giọng nói và đóng bìa vàng...",
    "/api/fetch_edit_new_link",
    {livevault_url: url, max_clips: maxC, product_key: pKey},
    btn
  );
}
function addCustomProductUI(btn) {
  const payload = {
    product_key: document.getElementById('cpKey').value.trim(),
    product_name: document.getElementById('cpName').value.trim(),
    cover_title: document.getElementById('cpTitle').value.trim(),
    benefit_1: document.getElementById('cpBen1').value.trim(),
    benefit_2: document.getElementById('cpBen2').value.trim(),
    dosage: document.getElementById('cpDosage').value.trim(),
    keywords: document.getElementById('cpKeywords').value.trim()
  };
  if (!payload.product_key || !payload.product_name) {
    showToast("Vui lòng nhập tối thiểu Mã sản phẩm và Tên sản phẩm!", true);
    return;
  }
  runAction("Thêm sản phẩm mới vào Từ điển", "Đang lưu sản phẩm mới...", "/api/add_custom_product", payload, btn);
}

loadStatus();
setInterval(loadStatus, 3000);
</script>
</body>
</html>"""


def ensure_livevault_recorder_8090_running():
    """Tu dong khoi chay LiveVault Recorder & iPhone Delivery (cong 8090) trong D:\\tiktok\\Tiktok_Tooler\\Luu neu chua chay."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 8090), timeout=0.8)
        s.close()
        return True
    except Exception:
        pass
    luu_dir = Path(r"D:\tiktok\Tiktok_Tooler\Luu")
    if not luu_dir.exists():
        return False
    try:
        log_f = open(str(DATA_DIR / "livevault_8090.log"), "a", encoding="utf-8")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        subprocess.Popen(
            ["py", "-3.12", "-u", "-m", "tiktok_recorder.colab_setup"],
            cwd=str(luu_dir),
            env=env,
            stdout=log_f,
            stderr=log_f,
            creationflags=creation_flags,
        )
        push_live_log("✓ Đã tự động khởi chạy dịch vụ thu video LiveVault Recorder (cổng 8090 & Telegram Bot).")
        return True
    except Exception as e:
        push_live_log(f"Lưu ý khởi chạy LiveVault 8090: {e}")
        return False


def main():
    init_db()
    # 1. Tu dong bat LiveVault Recorder (cong 8090)
    ensure_livevault_recorder_8090_running()

    # 2. Khoi chay local TLSv1.2 Rescue Proxy (127.0.0.1:8098 -> https://192.168.1.11:443) cho Dell iDRAC7 R620
    try:
        idrac_srv = ThreadingHTTPServer(("127.0.0.1", IDRAC_PROXY_PORT), IdracRescueProxyHandler)
        threading.Thread(target=idrac_srv.serve_forever, daemon=True).start()
    except Exception as e:
        print("Cảnh báo cổng iDRAC Proxy 8098:", e)

    # 3. Tu dong bat luon Cloudflare Tunnel tren Laptop (master.phamvuong.io.vn & idrac.phamvuong.io.vn -> 192.168.1.11)
    control_laptop_cloudflare_tunnel(enable=True)

    # 4. Dam bao bo hen gio Tu Dong 1 Tieng/Video luon duoc BAT
    cfg = get_settings()
    if not cfg.get("auto_scheduler_enabled", True):
        cfg["auto_scheduler_enabled"] = True
        SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    t = threading.Thread(target=background_scheduler_loop, daemon=True)
    t.start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), HubHandler)
    print("========================================================================")
    print(" TIKTOK AUTOHUB MASTER CONTROL CENTER v3.0")
    print(f" - Giao dien tai Laptop      : http://127.0.0.1:{PORT}")
    print(" - Dieu khien Master Tu Xa   : https://master.phamvuong.io.vn")
    print(" - Cuu ho iDRAC R620 (1.11)  : https://idrac.phamvuong.io.vn & https://idrac-rescue.phamvuong.io.vn")
    print(" - Cuu ho Proxmox (1.20)     : https://pve-rescue.phamvuong.io.vn")
    print("========================================================================")
    srv.serve_forever()


if __name__ == "__main__":
    main()
