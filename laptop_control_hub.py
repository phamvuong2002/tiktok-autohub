# -*- coding: utf-8 -*-
"""
TIKTOK AUTOHUB - STANDALONE LAPTOP CONTROLLER, AUTO-SAVE-DRAFT (LƯU NHÁP) & 1-HOUR POST REMINDER
Hoan thien theo dung yeu cau cua nguoi dung (khi Laptop + Oppo A57 di ra ngoai cung LAN, khac mang R630):
1. Ket noi Oppo A57 tren mang LAN moi (10.110.8.x):
   - Ho tro Nhap IP:Port Go loi khong day (khong can ma ghep noi 6 so vi da co khoa RSA)
   - Ho tro Cam cap USB 3 giay (tu bat cong 5555 + tu doc IP Wi-Fi moi + tu ket noi Wi-Fi)
   - Ho tro Tu bat IP khi Oppo A57 mo trang http://<IP-Laptop>:8099/mobile
2. Tu dong LUU NHAP (Save Draft) tren Oppo A57 kem Caption Tieng Viet CO DAU 100%:
   - Chuyen dung tai khoan (@suckhoeviet.2 / @suc.khoe.vang.268)
   - Day duy nhat 1 video vao Camera -> Mo TikTok -> Chon video #1 -> Dan Caption Tieng Viet CO DAU 100% (KEYCODE_PASTE 279) -> Bam 'Nháp' (188, 1540)!
3. Nhac lich dang moi 1 TIENG (60 phut / 1 video):
   - Moi 60 phut: Tu dong Luu Nhap bai tiep theo lên Oppo A57 (neu chua luu nhap) + Phat chuong & Hien Popup Nhac Dang tren Laptop
   - Nguoi dung chi can mo muc [Nháp] tren TikTok Oppo A57 -> Chon san pham GMV Max -> Bam [Đăng] -> Bam [✅ Đánh Dấu Đã Đăng]!
"""
import ctypes
import json
import threading
import time
import urllib.parse
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
from local_video_editor import EDITOR_STATUS, start_batch_fetch_and_edit

PORT = 8099
RUNTIME_STATE = {
    "last_action_time": datetime.now().strftime("%H:%M:%S"),
    "last_action_result": "Chế độ Lưu Nháp (Draft) kèm Caption Tiếng Việt có dấu 100% & Nhắc lịch đăng mỗi 1 tiếng đã sẵn sàng!",
    "next_reminder_epoch": time.time() + 3600,
    "r630_sync_status": {"r630_online": False, "cached_offline_ready": 0, "total_queue": 0},
    "oppo_status": {"connected": False, "serial": None, "mode": "NONE", "detail": "Đang kiểm tra..."},
}


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
    max_len = max(len(ch1), len(ch2))
    for i in range(max_len):
        if i < len(ch1):
            interleaved.append(ch1[i])
        if i < len(ch2):
            interleaved.append(ch2[i])

    base_time = datetime.now().replace(second=0, microsecond=0)
    for idx, item in enumerate(interleaved):
        slot_dt = base_time + timedelta(hours=idx)
        item["scheduled_1h_slot"] = (
            "Ngay bây giờ (Khung giờ hiện tại)" if idx == 0 else f"{slot_dt.strftime('%H:%M · %d/%m/%Y')} (Cách {idx}h)"
        )
        fname = Path(item.get("output_video", "")).name
        item["cached_offline"] = (CACHE_DIR / fname).exists()
    return interleaved


def trigger_1hour_draft_and_reminder() -> dict:
    """
    Khi den gio nhac (moi 1 tieng) hoac khi bam nut '[🔔 Lưu Nháp & Nhắc Đăng Ngay]':
    1. Neu bai dau tien chua Luu Nhap va Oppo A57 dang ket noi -> Tu dong Chuyen TK + Day Video + Dan Caption Tieng Viet Co Dau + Bam 'Nháp'!
    2. Phat chuong & Hien Popup nhac nguoi dung mo muc [Nháp] tren Oppo A57 -> Chon san pham -> Bam [Đăng]!
    """
    ready = get_ready_queue_with_1h_schedule()
    if not ready:
        return {"ok": False, "message": "Không còn video nào trong hàng chờ."}

    due_item = ready[0]
    draft_msg = "Video này đã được Lưu Nháp sẵn trên Oppo A57."
    res = {"ok": True, "item": due_item}

    oppo_now = quick_check_oppo_connected()
    if due_item.get("status") != "SAVED_DRAFT" and oppo_now.get("connected"):
        res = auto_save_draft_on_oppo(item_id=due_item["id"])
        draft_msg = res.get("message", "")
    elif not oppo_now.get("connected"):
        draft_msg = "⚠️ Lưu ý: Oppo A57 chưa kết nối ADB nên hệ thống chưa tự bấm Lưu Nháp được. Hãy kết nối Oppo A57 để hệ thống tự động Lưu Nháp!"

    RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
    RUNTIME_STATE["last_action_result"] = f"🔔 NHẮC LỊCH ĐĂNG (1 Tiếng/Video - {due_item['channel']}): {draft_msg}"

    popup_windows_reminder(
        "⏰ ĐẾN GIỜ ĐĂNG VIDEO TIKTOK TỪ MỤC [NHÁP] (1 TIẾNG / 1 VIDEO)",
        f"Đã đến khung giờ đăng bài tiếp theo!\n\n"
        f"• Tài khoản TikTok: {due_item['channel']}\n"
        f"• Sản phẩm cần chọn: {due_item['product_name']}\n"
        f"• Shop GMV Max ID: {due_item['seller_id']}\n\n"
        f"Trạng thái trên Oppo A57:\n{draft_msg}\n\n"
        f"👉 BẠN CHỈ CẦN LÀM 2 BƯỚC CUỐI TRÊN OPPO A57:\n"
        f"1) Mở mục [Nháp] trong Hồ sơ kênh {due_item['channel']} -> Chọn Sản Phẩm -> Bấm [Đăng].\n"
        f"2) Bấm nút màu xanh [✅ 2. Đánh Dấu Đã Đăng] trên bảng điều khiển để khóa chống trùng và hẹn nhắc 1 tiếng sau!",
    )
    return res


def background_scheduler_loop():
    init_db()
    last_sync_ts = 0.0
    while True:
        try:
            now = time.time()
            RUNTIME_STATE["oppo_status"] = quick_check_oppo_connected()

            if now - last_sync_ts >= 180:
                RUNTIME_STATE["r630_sync_status"] = sync_from_r630_to_laptop_cache()
                last_sync_ts = now

            cfg = get_settings()
            if cfg.get("auto_scheduler_enabled", True):
                if now >= RUNTIME_STATE["next_reminder_epoch"]:
                    trigger_1hour_draft_and_reminder()
                    interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
                    RUNTIME_STATE["next_reminder_epoch"] = time.time() + interval_sec
        except Exception as e:
            RUNTIME_STATE["last_action_result"] = f"Lỗi luồng nền: {e}"
        time.sleep(8)


class LaptopHubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data: dict, status: int = 200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        client_ip = self.client_address[0]

        # Neu Oppo A57 truy cap bat ky trang nao (/mobile hoac /auto_copy), tu dong ghi nhan IP cua Oppo A57 tren mang LAN moi!
        if client_ip not in ("127.0.0.1", "::1", get_laptop_lan_ip()):
            cfg = get_settings()
            if cfg.get("oppo_last_ip") != client_ip:
                cfg["oppo_last_ip"] = client_ip
                SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            if not quick_check_oppo_connected().get("connected"):
                threading.Thread(target=scan_and_connect_single_ip, args=(client_ip,), daemon=True).start()

        if parsed.path == "/api/status":
            cfg = get_settings()
            oppo = quick_check_oppo_connected()
            RUNTIME_STATE["oppo_status"] = oppo
            ledger = get_ledger_history(30)
            ready_queue = get_ready_queue_with_1h_schedule()
            cached_count = sum(1 for x in ready_queue if x.get("cached_offline"))
            RUNTIME_STATE["r630_sync_status"]["cached_offline_ready"] = cached_count
            RUNTIME_STATE["r630_sync_status"]["total_queue"] = len(ready_queue)

            rem_sec = max(0, int(RUNTIME_STATE["next_reminder_epoch"] - time.time()))
            r630_svcs = {"tiktok-worker": True, "tiktok-portal": True, "cloudflared-tiktok": True}
            try:
                import urllib.request
                r630_base = cfg.get("r630_url", "https://tiktok.phamvuong.io.vn").rstrip("/")
                raw_s = urllib.request.urlopen(f"{r630_base}/api/r630_service_status", timeout=2.5).read().decode("utf-8")
                r630_svcs = json.loads(raw_s).get("services", r630_svcs)
            except Exception:
                pass
            return self._send_json({
                "settings": cfg,
                "lan_ip": get_laptop_lan_ip(),
                "runtime": RUNTIME_STATE,
                "bridge": get_bridge_status(),
                "r630_services": r630_svcs,
                "editor": EDITOR_STATUS,
                "next_wait_seconds": rem_sec,
                "ledger": ledger,
                "ready_queue": ready_queue[:24],
            })

        if parsed.path == "/auto_copy":
            # Trang Full-Screen 720x1600 phuc vu copy_vietnamese_to_oppo_clipboard()
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
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
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
            res = auto_connect_oppo(hint_ip=hint)
            RUNTIME_STATE["oppo_status"] = res
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("detail", "")
            return self._send_json(res)

        if parsed.path == "/api/pair_oppo":
            res = pair_oppo_wireless(
                body.get("pair_ip_port", ""),
                body.get("pair_code", ""),
                body.get("main_ip_port", ""),
            )
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            return self._send_json(res)

        if parsed.path == "/api/sync_r630":
            res = sync_from_r630_to_laptop_cache()
            RUNTIME_STATE["r630_sync_status"] = res
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = (
                f"Kho Offline Laptop: {res['cached_offline_ready']} video sẵn sàng (R630 {'Online' if res['r630_online'] else 'Đang khác mạng - Dùng Cache Offline'})."
            )
            return self._send_json(res)

        if parsed.path == "/api/test_switch":
            ch = body.get("channel", "@suckhoeviet.2")
            conn = auto_connect_oppo()
            if not conn["connected"]:
                return self._send_json({"ok": False, "message": conn["detail"]})
            ok, msg = ensure_correct_tiktok_account(conn["serial"], ch)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = msg
            return self._send_json({"ok": ok, "message": msg})

        if parsed.path == "/api/save_draft_on_oppo":
            item_id = body.get("item_id") or None
            ch = body.get("channel") or None
            res = auto_save_draft_on_oppo(item_id=item_id, channel=ch)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            return self._send_json(res)

        if parsed.path == "/api/mark_posted":
            item_id = body.get("item_id", "")
            res = mark_video_as_posted(item_id)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            if res.get("ok"):
                cfg = get_settings()
                interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
                RUNTIME_STATE["next_reminder_epoch"] = time.time() + interval_sec
            return self._send_json(res)

        if parsed.path == "/api/trigger_reminder_now":
            res = trigger_1hour_draft_and_reminder()
            return self._send_json(res)

        if parsed.path == "/api/start_remote_bridge":
            custom_wan = body.get("wan_ip_port", "")
            res = start_cloudflare_login_and_ssh_tunnel(custom_wan)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("last_bridge_msg", "")
            return self._send_json(res)

        if parsed.path == "/api/fetch_edit_new_link":
            lv_url = body.get("livevault_url", "")
            max_c = int(body.get("max_clips", 5))
            p_key = body.get("product_key", "AUTO")
            res = start_batch_fetch_and_edit(lv_url, max_clips=max_c, forced_product_key=p_key)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            return self._send_json(res)

        if parsed.path == "/api/master_control":
            target = body.get("target", "")
            action = body.get("action", "")
            import subprocess, urllib.request
            from oppo_auto_poster import run_adb
            msg = ""
            if target == "r630_worker":
                r630_base = get_settings().get("r630_url", "https://tiktok.phamvuong.io.vn").rstrip("/")
                try:
                    req = urllib.request.Request(f"{r630_base}/api/r630_service?action={action}&service=tiktok-worker", method="POST")
                    urllib.request.urlopen(req, timeout=6).read()
                    msg = f"✓ Đã {'BẬT' if action=='start' else 'TẮT'} Worker Tự Cắt Video 24/7 trên Server Dell R630!"
                except Exception as e:
                    msg = f"Lỗi điều khiển Worker R630: {e}"
            elif target == "adb_server":
                if action == "stop":
                    run_adb(["kill-server"])
                    msg = "⏹️ Đã TẮT dịch vụ ADB Server trên Laptop (Ngắt kết nối Oppo A57)."
                else:
                    run_adb(["kill-server"])
                    run_adb(["start-server"])
                    msg = "▶️ Đã BẬT lại dịch vụ ADB Server trên Laptop (Sẵn sàng kết nối Oppo A57)."
            elif target == "laptop_hub" and action == "stop":
                self._send_json({"ok": True, "message": "🛑 Đang tắt hoàn toàn Trạm Điều Khiển Laptop (Port 8099). Để bật lại, hãy mở file Master-Control-Station.cmd hoặc Start-TikTok-AutoHub.cmd!"})
                threading.Thread(target=lambda: (time.sleep(0.8), os._exit(0)), daemon=True).start()
                return
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = msg
            return self._send_json({"ok": True, "message": msg})

        if parsed.path == "/api/update_settings":
            cfg = get_settings()
            for k in ("auto_scheduler_enabled", "interval_minutes"):
                if k in body:
                    cfg[k] = body[k]
            SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            if cfg.get("auto_scheduler_enabled"):
                RUNTIME_STATE["next_reminder_epoch"] = time.time() + int(cfg.get("interval_minutes", 60)) * 60
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = (
                f"Đã cập nhật bộ nhắc đăng & lưu nháp 1 tiếng/video: {'ĐANG BẬT' if cfg['auto_scheduler_enabled'] else 'ĐANG TẮT'}"
            )
            return self._send_json({"ok": True, "settings": cfg})

        self.send_error(404)

    def _build_mobile_oppo_card_html(self, item_id: str, client_ip: str) -> str:
        ready = get_ready_queue_with_1h_schedule()
        item = next((x for x in ready if x.get("id") == item_id), ready[0] if ready else None)
        if not item:
            return "<h2 style='color:white;background:#0b0f19;padding:20px;font-family:sans-serif;'>Đã hoàn tất toàn bộ video trong hàng chờ!</h2>"

        fname = Path(item.get("output_video", "")).name
        cap_json = json.dumps(item["caption_seo"], ensure_ascii=False)
        return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oppo A57 — Kết Nối LAN & Lưu Nháp TikTok</title>
<style>
  body {{ margin:0; padding:16px; background:#0b0f19; color:#f8fafc; font-family:'Segoe UI',system-ui,sans-serif; }}
  .card {{ background:#131b2e; border:2px solid #fde047; border-radius:16px; padding:18px; max-width:520px; margin:0 auto; }}
  .ch {{ font-size:20px; font-weight:800; color:#fde047; margin-bottom:6px; }}
  .sub {{ font-size:13px; color:#94a3b8; margin-bottom:12px; line-height:1.5; }}
  .cap-box {{ background:#090d16; border:1px solid #334155; border-radius:12px; padding:14px;
              font-size:15px; line-height:1.55; white-space:pre-line; color:#fff; margin-bottom:14px; }}
  .btn {{ width:100%; border:none; border-radius:12px; padding:15px; font-size:16px; font-weight:800;
          cursor:pointer; margin-bottom:10px; display:block; text-align:center; text-decoration:none; }}
  .btn-yellow {{ background:#fde047; color:#000; }}
  .btn-green {{ background:#22c55e; color:#052e16; }}
</style>
</head>
<body>
<div class="card">
  <div style="background:rgba(34,197,94,0.18);border:1px solid #22c55e;color:#4ade80;padding:8px 12px;border-radius:8px;font-size:13px;font-weight:700;margin-bottom:10px;">
    📡 Laptop đã tự động nhận diện IP Oppo A57 của bạn trên mạng LAN mới: <code>{client_ip}</code>
  </div>
  <div class="ch">🎯 Kênh: {item['channel']}</div>
  <div class="sub">
    <b>Sản phẩm gắn giỏ:</b> {item['product_name']}<br>
    <b>Shop GMV Max ID:</b> <code>{item['seller_id']}</code><br>
    <b>Trạng thái:</b> {item.get('status', 'READY')}
  </div>

  <div class="cap-box">{item['caption_seo']}</div>

  <button class="btn btn-yellow" id="btn-copy" onclick="copyVietnameseCaption()">
    📋 COPY CAPTION TIẾNG VIỆT CÓ DẤU (DỰ PHÒNG)
  </button>

  <button class="btn btn-green" id="btn-done" onclick="markPosted('{item['id']}')">
    ✅ ĐÁNH DẤU ĐÃ ĐĂNG TỪ NHÁP (HẸN NHẮC 1 TIẾNG SAU)
  </button>
</div>

<script>
const CAPTION_TEXT = {cap_json};
function copyVietnameseCaption() {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(CAPTION_TEXT);
  }}
  const ta = document.createElement('textarea');
  ta.value = CAPTION_TEXT;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  const b = document.getElementById('btn-copy');
  b.textContent = '✓ ĐÃ COPY CAPTION TIẾNG VIỆT CÓ DẤU!';
  b.style.background = '#4ade80';
}}

async function markPosted(itemId) {{
  const r = await fetch('/api/mark_posted', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{item_id: itemId}})
  }});
  const res = await r.json();
  alert(res.message);
  window.location.href = '/mobile';
}}
</script>
</body>
</html>"""

    def _build_dashboard_html(self) -> str:
        return """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TikTok AutoHub — Tự Động Lưu Nháp (Caption Tiếng Việt) & Nhắc Lịch 1 Tiếng/Video</title>
<style>
  :root {
    --bg: #0b0f19; --card: #131b2e; --border: #26324d;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #fde047;
    --green: #22c55e; --red: #ef4444; --blue: #38bdf8;
  }
  * { box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { margin: 0; padding: 20px; background: var(--bg); color: var(--text); }
  .wrap { max-width: 1360px; margin: 0 auto; }
  .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
            background: linear-gradient(135deg, #162038, #0f172a); padding: 18px 22px; border-radius: 14px;
            border: 1px solid var(--border); margin-bottom: 18px; }
  .title { font-size: 21px; font-weight: 800; color: var(--accent); }
  .sub { font-size: 13px; color: var(--muted); margin-top: 4px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(390px, 1fr)); gap: 16px; margin-bottom: 18px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
  .card h3 { margin: 0 0 10px 0; font-size: 16px; color: var(--accent); }
  .badge { display: inline-block; padding: 5px 11px; border-radius: 99px; font-size: 12px; font-weight: 700; }
  .b-ok { background: rgba(34,197,94,0.18); color: #4ade80; border: 1px solid #22c55e; }
  .b-warn { background: rgba(239,68,68,0.18); color: #f87171; border: 1px solid #ef4444; }
  .b-info { background: rgba(56,189,248,0.18); color: #38bdf8; border: 1px solid #0284c7; }
  .b-draft { background: rgba(253,224,71,0.18); color: #fde047; border: 1px solid #eab308; }
  .btn { cursor: pointer; border: none; border-radius: 9px; padding: 9px 13px; font-weight: 700; font-size: 13px;
         transition: 0.15s; display: inline-flex; align-items: center; gap: 6px; text-decoration: none; }
  .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .btn-yellow { background: var(--accent); color: #000; }
  .btn-green { background: var(--green); color: #052e16; }
  .btn-blue { background: var(--blue); color: #082f49; }
  .btn-dark { background: #1e293b; color: var(--text); border: 1px solid var(--border); }
  input { background: #0b1120; border: 1px solid var(--border); color: var(--text); padding: 9px 12px; border-radius: 8px; font-size: 13px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 10px; }
  .log-bar { background: #0f172a; border-left: 4px solid var(--accent); padding: 12px 16px;
             border-radius: 8px; margin-bottom: 18px; font-size: 14px; }
  .timer-box { font-size: 23px; font-weight: 800; color: #4ade80; margin: 8px 0; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
  th, td { text-align: left; padding: 12px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  .mono { font-family: Consolas, monospace; font-size: 12px; color: #38bdf8; }
  .cap-card { background: #090d16; border: 1px solid #26324d; border-radius: 10px; padding: 10px 12px;
              white-space: pre-line; font-size: 13px; line-height: 1.5; color: #f8fafc; min-width: 350px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <div class="title">⚡ TIKTOK AUTOHUB — TỰ ĐỘNG LƯU NHÁP (CAPTION TIẾNG VIỆT) & NHẮC LỊCH 1 TIẾNG / VIDEO</div>
      <div class="sub">Chế độ Đi Ra Ngoài (Offline Cache): Tự chuyển tài khoản • Đẩy Video • Dán Caption Tiếng Việt có dấu • Bấm Lưu Nháp • Nhắc bạn chọn Sản phẩm & Đăng mỗi 1 tiếng</div>
    </div>
    <div id="top-badges" class="row"></div>
  </div>

  <div class="log-bar">
    <strong>Trạng thái thực thi:</strong> <span id="last-msg">Đang tải...</span>
  </div>

  <!-- TRAM KIEM SOAT TONG THE: BAT / TAT BANG TAY TAT CA CHUONG TRINH (SERVER R630 + LAPTOP + OPPO A57) -->
  <div class="card" style="margin-bottom:18px; border:2px solid #38bdf8; background:linear-gradient(135deg, #0f172a, #131b2e);">
    <h3>🎛️ Trạm Kiểm Soát Tổng Thể — Bật / Tắt Bằng Tay Tất Cả Chương Trình (Không Cần Nhờ AI)</h3>
    <div style="font-size:13px; color:var(--muted); margin-bottom:12px;">
      Bạn có thể chủ động <b>BẬT / TẮT bằng tay</b> từng thành phần trên Server R630 và trên Laptop ngay tại đây (hoặc mở file <code>C:\TikTok_AutoHub\Master-Control-Station.cmd</code> khi muốn bật lại từ đầu):
    </div>
    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(290px, 1fr)); gap:12px; font-size:13px;">
      <!-- SWITCH 1: SERVER R630 WORKER -->
      <div style="background:#090d16; padding:12px; border-radius:10px; border:1px solid var(--border);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <b>🖥️ 1. [Server R630] Worker Tự Cắt Video 24/7</b>
          <span id="sw-r630-badge" class="badge b-ok">ĐANG BẬT</span>
        </div>
        <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">
          Chạy trên Container 240 (<code>192.168.1.240</code> / <code>tiktok.phamvuong.io.vn</code>): Tự quét LiveVault & render video mới.
        </div>
        <div class="row">
          <button class="btn btn-green" onclick="masterCtrl('r630_worker','start')">▶️ Bật Worker R630</button>
          <button class="btn btn-dark" onclick="masterCtrl('r630_worker','stop')">⏹️ Tắt Worker R630</button>
          <a class="btn btn-blue" href="https://tiktok.phamvuong.io.vn" target="_blank">🌐 Mở Web R630</a>
        </div>
      </div>

      <!-- SWITCH 2: LAPTOP 1H SCHEDULER -->
      <div style="background:#090d16; padding:12px; border-radius:10px; border:1px solid var(--border);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <b>💻 2. [Laptop] Bộ Nhắc Lịch & Lưu Nháp 1 Tiếng</b>
          <span id="sw-sched-badge" class="badge b-ok">ĐANG BẬT</span>
        </div>
        <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">
          Đếm ngược mỗi 60 phút để tự đẩy video sang Nháp Oppo A57 & bật chuông nhắc bạn chọn sản phẩm.
        </div>
        <div class="row">
          <button class="btn btn-green" onclick="apiPost('/api/update_settings',{auto_scheduler_enabled:true})">▶️ Bật Hẹn Giờ 1h</button>
          <button class="btn btn-dark" onclick="apiPost('/api/update_settings',{auto_scheduler_enabled:false})">⏹️ Tắt Hẹn Giờ 1h</button>
        </div>
      </div>

      <!-- SWITCH 3: OPPO A57 ADB SERVICE -->
      <div style="background:#090d16; padding:12px; border-radius:10px; border:1px solid var(--border);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <b>📱 3. [Oppo A57] Dịch Vụ Cổng Kết Nối ADB</b>
          <span id="sw-adb-badge" class="badge b-warn">KIỂM TRA</span>
        </div>
        <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">
          Cầu nối điều khiển điện thoại Oppo A57 (chuyển 4 tài khoản, đẩy video, dán Caption Tiếng Việt & bấm Nháp).
        </div>
        <div class="row">
          <button class="btn btn-green" onclick="masterCtrl('adb_server','start')">▶️ Khởi Động Lại ADB</button>
          <button class="btn btn-dark" onclick="masterCtrl('adb_server','stop')">⏹️ Ngắt & Tắt ADB</button>
        </div>
      </div>

      <!-- SWITCH 4: SHUTDOWN LAPTOP HUB -->
      <div style="background:#090d16; padding:12px; border-radius:10px; border:1px solid var(--border);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <b>🛑 4. [Laptop] Trạm Điều Khiển Chính (Port 8099)</b>
          <span class="badge b-ok">ĐANG CHẠY</span>
        </div>
        <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">
          Khi nghỉ làm việc, bấm nút dưới để tắt hẳn chương trình chạy ngầm trên Laptop (Mở lại bằng <code>Start-TikTok-AutoHub.cmd</code>).
        </div>
        <div class="row">
          <button class="btn" style="background:#ef4444;color:#fff;width:100%;justify-content:center;" onclick="if(confirm('Bạn muốn tắt hẳn Trạm Điều Khiển trên Laptop (Port 8099)? Khi cần bật lại, chỉ cần mở file Start-TikTok-AutoHub.cmd!')) masterCtrl('laptop_hub','stop')">
            🛑 Tắt Hẳn Chương Trình Trên Laptop
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- HOP HUONG DAN 3 BUOC TRUC QUAN TREN GIAO DIEN & CO CHE CHONG TRUNG 4 LOP -->
  <div class="card" style="margin-bottom:18px; border:1px solid #eab308; background:linear-gradient(135deg, #161f33, #0f172a);">
    <h3>📖 Hướng Dẫn Sử Dụng Trực Tiếp Trên Giao Diện Này (3 Bước Chuẩn & Chống Đăng Trùng Tuyệt Đối 4 Lớp)</h3>
    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; font-size:13px; line-height:1.55;">
      <div style="background:#090d16; padding:12px; border-radius:10px; border-left:4px solid #38bdf8;">
        <b style="color:#38bdf8;">BƯỚC 1 — Kết nối Oppo A57 (Ô số 1 bên dưới):</b><br>
        • Khi đi ra ngoài (khác mạng R630), bạn chỉ cần <b>cắm dây cáp USB</b> từ Oppo A57 vào Laptop (hoặc bật <i>Điểm phát sóng cá nhân</i> trên Oppo A57) rồi bấm nút vàng <b>[🔌 Tự Động Tìm & Nối Oppo A57]</b>.<br>
        • Nhìn góc phải trên cùng hiện nhãn xanh <b>📱 Oppo A57: ĐÃ KẾT NỐI</b> là sẵn sàng.
      </div>
      <div style="background:#090d16; padding:12px; border-radius:10px; border-left:4px solid #fde047;">
        <b style="color:#fde047;">BƯỚC 2 — Tự Động Lưu Nháp Kèm Caption Tiếng Việt:</b><br>
        • Ở bảng <b>Danh Sách Video Lên Lịch</b> bên dưới, bấm nút vàng <b>[📝 1. Tự Động Đẩy Video + Dán Tiếng Việt & Lưu Nháp]</b> ở bài đầu tiên (hoặc để hệ thống tự chạy mỗi 60 phút).<br>
        • Hệ thống sẽ tự kiểm tra chống trùng, chuyển đúng kênh (<code>@suckhoeviet.2</code> / <code>@suc.khoe.vang.268</code>), đẩy duy nhất 1 video sang máy, dán <b>Caption Tiếng Việt có dấu 100%</b> và bấm <b>Lưu Nháp</b> trên TikTok!
      </div>
      <div style="background:#090d16; padding:12px; border-radius:10px; border-left:4px solid #22c55e;">
        <b style="color:#4ade80;">BƯỚC 3 — Chọn Sản Phẩm Từ Nháp & Đánh Dấu Đã Đăng:</b><br>
        • Khi Laptop đổ chuông & hiện bảng nhắc (mỗi 1 tiếng), bạn mở mục <b>[Nháp]</b> trong Hồ sơ TikTok trên Oppo A57 -> Chọn <b>Thêm liên kết (Sản phẩm GMV Max)</b> -> Bấm <b>[Đăng]</b>.<br>
        • Đăng xong, bạn bấm ngay nút xanh <b>[✅ 2. Đánh Dấu Đã Đăng Từ Nháp]</b> trên bảng dưới để <b>xóa vĩnh viễn file video đã đăng</b>, khóa mã <code>SHA-256</code> và bắt đầu đếm ngược 60 phút cho bài kế tiếp!
      </div>
    </div>
  </div>

  <div class="grid">
    <!-- CARD 1: KET NOI & GHEP NOI OPPO A57 TRUC TIEP (DAY DU NUT TU TAY BAM) -->
    <div class="card">
      <h3>📱 1. Hộp Kết Nối & Ghép Nối Oppo A57 (Tự Tay Nhấn Kết Nối)</h3>
      <div id="oppo-detail" style="font-size:13px; color:var(--muted); margin-bottom:10px;">Đang kiểm tra...</div>

      <!-- NUT 1: TU DONG TIM & NOI -->
      <div class="row" style="margin-bottom:10px;">
        <button class="btn btn-yellow" style="width:100%; justify-content:center; padding:11px;" onclick="connectOppo('')">
          🔌 Tự Động Tìm & Nối Oppo A57 (USB / mDNS / Quét LAN)
        </button>
      </div>

      <!-- HOP A: NOI TRUC TIEP IP:PORT (KHONG CAN MA 6 SO) -->
      <div style="background:#090d16; border:1px solid var(--border); border-radius:10px; padding:10px 12px; margin-bottom:10px;">
        <div style="font-size:12px; font-weight:700; color:var(--blue); margin-bottom:6px;">
          ⚡ Cách A — Nối Trực Tiếp Bằng Địa Chỉ IP:Port (Trên màn hình Gỡ lỗi không dây):
        </div>
        <div class="row" style="margin-top:4px;">
          <input id="manual-ip" placeholder="Nhập IP:Port chính (vd: 10.110.8.99:41235)" style="flex:1; min-width:190px;">
          <button class="btn btn-green" onclick="connectOppo(document.getElementById('manual-ip').value)">⚡ Kết Nối IP:Port</button>
        </div>
      </div>

      <!-- HOP B: GHEP NOI BANG MA 6 SO (GIONG HET HOP TRUOC DE TU TAY NHAN) -->
      <div style="background:#090d16; border:1px solid #eab308; border-radius:10px; padding:10px 12px;">
        <div style="font-size:12px; font-weight:700; color:var(--accent); margin-bottom:6px;">
          🔗 Cách B — Ghép Nối Thiết Bị Bằng Mã 6 Số (Khi đổi mạng mới cần ghép nối lại):
        </div>
        <div class="row" style="margin-top:4px;">
          <input id="pair-ip" placeholder="IP:Port ghép nối (vd: 10.110.8.99:38123)" style="flex:1; min-width:170px;">
          <input id="pair-code" placeholder="Mã 6 số (vd: 652918)" style="width:140px;">
        </div>
        <div class="row" style="margin-top:8px;">
          <input id="pair-main-port" placeholder="IP:Port chính bên ngoài (tùy chọn, bỏ trống sẽ tự quét)" style="flex:1;">
          <button class="btn btn-yellow" onclick="pairOppo()">🔗 Ghép Nối & Kết Nối Ngay</button>
        </div>
      </div>
    </div>

    <!-- CARD 2: BO NHAC LICH DANG & TU DONG LUU NHAP MOI 1 TIENG -->
    <div class="card">
      <h3>⏰ 2. Bộ Nhắc Lịch Đăng & Tự Động Lưu Nháp (1 Tiếng / Video)</h3>
      <div style="font-size:13px; color:var(--muted);">
        Mỗi 60 phút, hệ thống tự động đẩy bài tiếp theo vào mục <b>[Nháp]</b> trên Oppo A57 (kèm Caption Tiếng Việt có dấu) và bật chuông + Popup nhắc bạn chọn sản phẩm & bấm Đăng:
      </div>
      <div class="timer-box" id="countdown-timer">⏳ Đang tính thời gian...</div>
      <div class="row">
        <button class="btn btn-yellow" onclick="triggerReminderNow()">📝 Lưu Nháp & Nhắc Đăng Bài Tiếp Theo Ngay</button>
        <button id="btn-toggle-sched" class="btn btn-dark" onclick="toggleScheduler()">⏸️ Tắt Nhắc Tự Động</button>
      </div>
    </div>

    <!-- CARD 3: KHO VIDEO OFFLINE & TEST CHUYEN TAI KHOAN -->
    <div class="card">
      <h3>📦 3. Kho Video Offline Trên Laptop & Chuyển 4 Tài Khoản</h3>
      <div id="cache-detail" style="font-size:13px; color:var(--muted); margin-bottom:10px;">Đang kiểm tra...</div>
      <div class="row">
        <button class="btn btn-dark" onclick="testSwitch('@suckhoeviet.2')">🔄 Chuyển sang @suckhoeviet.2</button>
        <button class="btn btn-dark" onclick="testSwitch('@suc.khoe.vang.268')">🔄 Chuyển sang @suc.khoe.vang.268</button>
      </div>
      <div class="row">
        <button class="btn btn-blue" onclick="syncR630()">📥 Kiểm Tra / Đồng Bộ Kho Video R630</button>
      </div>
    </div>
  </div>

  <!-- HANG 2: HOP THU & EDIT LOAT VIDEO MOI TU LINK LIVEVAULT + HOP KET NOI SERVER NHA TU XA (PORT 4898 / TUNNEL) -->
  <div class="grid">
    <!-- CARD 4: THU & EDIT TU DONG LOAT VIDEO MOI TU LINK LIVEVAULT MOI -->
    <div class="card" style="border:1px solid #38bdf8;">
      <h3>🎬 4. Thu, Cắt & Edit Tự Động Loạt Video Mới (Từ Link LiveVault Mới)</h3>
      <div style="font-size:13px; color:var(--muted); margin-bottom:8px;">
        Dán đường link thu video mới (ví dụ: <code>http://192.168.1.75:8090/d/...</code> hoặc <code>http://127.0.0.1:8090/d/...</code>). Hệ thống sẽ tự tải clip mới, lọc trùng 4 lớp, cắt bỏ đoạn cuối vi phạm, đảo Hook 3.5s, đóng khung chữ Vàng chữ Đen, viết Caption Tiếng Việt có dấu + 5 Hashtag và đưa lên <b>ĐẦU bảng lịch đăng 1 tiếng</b>:
      </div>
      <div class="row">
        <input id="new-lv-url" placeholder="Dán link thu video LiveVault mới vào đây (http://...:8090/d/...)" style="flex:1; min-width:260px;">
      </div>
      <div class="row">
        <select id="new-lv-count" style="background:#0b1120;border:1px solid var(--border);color:var(--text);padding:9px;border-radius:8px;font-size:13px;">
          <option value="3">Cắt 3 clip mới nhất (= 6 video cho 2 kênh)</option>
          <option value="5" selected>Cắt 5 clip mới nhất (= 10 video cho 2 kênh)</option>
          <option value="10">Cắt 10 clip mới nhất (= 20 video cho 2 kênh)</option>
          <option value="1">Chỉ cắt 1 clip trong link (?clip=...)</option>
        </select>
        <select id="new-lv-prod" style="background:#0b1120;border:1px solid var(--border);color:var(--text);padding:9px;border-radius:8px;font-size:13px;flex:1;">
          <option value="AUTO">🤖 Tự nhận diện giọng nói Bác Chường (Auto AI)</option>
          <option value="bokhop_chondro">Viên uống Bổ Khớp Chondro-Aid Pháp</option>
          <option value="daday_baotu">Hỗn dịch Dạ Dày & Bao Tử</option>
          <option value="giaidoc_gan">Viên uống Giải Độc Gan & Hạ Men Gan</option>
          <option value="matngu_bonao">Viên uống Giấc Ngủ & Tuần Hoàn Não</option>
        </select>
      </div>
      <div class="row" style="margin-top:10px;">
        <button class="btn btn-yellow" style="width:100%;justify-content:center;padding:11px;" onclick="startFetchEditNewLink()">
          🎬 Bắt Đầu Thu, Cắt & Edit Loạt Video Mới Đưa Lên Đầu Lịch Đăng
        </button>
      </div>
      <div id="editor-status-box" style="margin-top:10px;padding:10px;background:#090d16;border-radius:8px;border:1px solid var(--border);font-size:13px;color:#4ade80;">
        Sẵn sàng nhận link thu video mới.
      </div>
    </div>

    <!-- CARD 5: KET NOI TU XA VE SERVER NHA (R620/R630 QUA PORT 4898 & CLOUDFLARE TUNNEL) -->
    <div class="card" style="border:1px solid #22c55e;">
      <h3>🌐 5. Kết Nối Từ Xa Về Server Ở Nhà (Port 4898 Đã Thoát CGNAT & Cầu Nối ssh.phamvuong.io.vn)</h3>
      <div id="bridge-detail" style="font-size:13px; color:var(--muted); margin-bottom:10px; line-height:1.55;">
        Đang kiểm tra trạng thái cầu nối về Server nhà...
      </div>
      <div class="row">
        <button class="btn btn-green" style="width:100%;justify-content:center;padding:11px;" onclick="startRemoteBridge('')">
          🌐 Mở Trình Duyệt Xác Thực & Bật Đường Hầm Nối Về Server Nhà (ssh.phamvuong.io.vn -> R620/R630)
        </button>
      </div>
      <div class="row" style="margin-top:10px;">
        <input id="wan-4898-input" placeholder="Hoặc nhập IP WAN hiện tại của nhà:4898 (vd: 115.77.xx.xx:4898)" style="flex:1;">
        <button class="btn btn-blue" onclick="startRemoteBridge(document.getElementById('wan-4898-input').value)">
          🔗 Kiểm Tra Port 4898
        </button>
      </div>
      <div style="font-size:12px; color:var(--muted); margin-top:10px; line-height:1.5;">
        • <b>Giải thích về Port 4898 của nhà bạn:</b> Router Viettel ở nhà đã thoát CGNAT và đang mở NAT <code>WAN :4898 -> 192.168.1.148:443</code>, đồng thời máy chủ nhà có sẵn đường hầm <code>ssh.phamvuong.io.vn</code>.<br>
        • Khi bạn bấm nút xanh ở trên và bấm <b>Approve</b> trên trình duyệt, Laptop sẽ tự động lấy IP WAN mới nhất của nhà và nối thông thẳng về <b>Server R620/R630 (`192.168.1.240:8088` & Proxmox `192.168.1.20:8006`)</b>!
      </div>
    </div>
  </div>

  <!-- BANG LICH DANG 1 TIENG / 1 VIDEO + NUT TU DONG LUU NHAP & DANH DAU DA DANG -->
  <div class="card" style="margin-bottom:18px;">
    <h3>📅 Danh Sách Video Lên Lịch (1 Tiếng / 1 Video) — Tự Động Lưu Nháp & Đánh Dấu Đã Đăng</h3>
    <table>
      <thead>
        <tr>
          <th style="width:185px;">Khung Giờ (Cách 1h) & Kênh</th>
          <th style="width:240px;">Sản Phẩm Cần Chọn Khi Đăng</th>
          <th>Caption Tiếng Việt Có Dấu + 5 Hashtag (Tự động dán vào Nháp)</th>
          <th style="width:300px;">Thao Tác Tự Động Lưu Nháp & Đánh Dấu Đăng</th>
        </tr>
      </thead>
      <tbody id="queue-tbody"></tbody>
    </table>
  </div>

  <!-- BANG SO CAI CHONG DANG TRUNG 3 LOP -->
  <div class="card">
    <h3>🛡️ Sổ Cái Chống Đăng Trùng 3 Lớp (Các Video Đã Đăng Từ Nháp — Khóa Cứng SHA-256)</h3>
    <table>
      <thead>
        <tr>
          <th>Thời gian đăng</th>
          <th>Tài khoản</th>
          <th>Clip Gốc</th>
          <th>Sản phẩm</th>
          <th>Mã Băm Video (SHA-256)</th>
          <th>Trạng thái</th>
        </tr>
      </thead>
      <tbody id="ledger-tbody"></tbody>
    </table>
  </div>
</div>

<script>
let currentSettings = {};
let remainingSeconds = 3600;
let queueMap = {};

function formatMMSS(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')} phút ${String(s).padStart(2, '0')} giây`;
}

setInterval(() => {
  if (remainingSeconds > 0) remainingSeconds--;
  const el = document.getElementById('countdown-timer');
  if (el) {
    el.textContent = currentSettings.auto_scheduler_enabled
      ? `⏳ Nhắc đăng bài tiếp theo sau: ${formatMMSS(remainingSeconds)}`
      : `⏸️ Đang tạm dừng bộ nhắc tự động`;
  }
}, 1000);

async function refreshStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    currentSettings = data.settings || {};
    remainingSeconds = data.next_wait_seconds || 0;
    const oppo = data.runtime.oppo_status || {};
    const r630 = data.runtime.r630_sync_status || {};

    document.getElementById('last-msg').textContent =
      `[${data.runtime.last_action_time}] ${data.runtime.last_action_result}`;

    const badges = [];
    if (oppo.connected) {
      badges.push(`<span class="badge b-ok">📱 Oppo A57: ĐÃ KẾT NỐI (${oppo.serial} • ${oppo.mode})</span>`);
    } else {
      badges.push(`<span class="badge b-warn">📱 Oppo A57: CHƯA KẾT NỐI TRÊN MẠNG MỚI</span>`);
    }
    badges.push(`<span class="badge b-info">📦 Kho Offline Laptop: ${r630.cached_offline_ready || 0} Video sẵn sàng</span>`);
    badges.push(`<span class="badge b-ok">🛡️ Đã Đăng & Khóa Chống Trùng: ${(data.ledger || []).length} Video</span>`);
    document.getElementById('top-badges').innerHTML = badges.join('');

    document.getElementById('oppo-detail').innerHTML = oppo.connected
      ? `<span style="color:#4ade80;font-weight:700;">✓ Đã kết nối Oppo A57 (${oppo.serial})</span> — Sẵn sàng tự động Lưu Nháp!`
      : `<span style="color:#f87171;">${oppo.detail || 'Chưa kết nối'}</span>`;

    document.getElementById('cache-detail').innerHTML =
      `Đang dùng Kho Video Offline trên Laptop (<code>C:\\TikTok_AutoHub\\video_cache</code>): <b>${r630.cached_offline_ready || 0}</b> video đã tải sẵn (Hoạt động độc lập không cần R630).`;

    if (data.r630_services) {
      const wOn = data.r630_services['tiktok-worker'];
      const rBadge = document.getElementById('sw-r630-badge');
      if (rBadge) {
        rBadge.textContent = wOn ? '🟢 ĐANG BẬT' : '🔴 ĐANG TẮT';
        rBadge.className = wOn ? 'badge b-ok' : 'badge b-warn';
      }
    }
    const sBadge = document.getElementById('sw-sched-badge');
    if (sBadge) {
      sBadge.textContent = currentSettings.auto_scheduler_enabled ? '🟢 ĐANG BẬT' : '🔴 ĐANG TẮT';
      sBadge.className = currentSettings.auto_scheduler_enabled ? 'badge b-ok' : 'badge b-warn';
    }
    const aBadge = document.getElementById('sw-adb-badge');
    if (aBadge) {
      aBadge.textContent = oppo.connected ? '🟢 ĐÃ KẾT NỐI' : '⚪ CHỜ KẾT NỐI';
      aBadge.className = oppo.connected ? 'badge b-ok' : 'badge b-warn';
    }

    if (data.editor) {
      const edBox = document.getElementById('editor-status-box');
      if (edBox) {
        edBox.innerHTML = data.editor.is_running
          ? `<b style="color:#fde047;">⏳ ĐANG XỬ LÝ:</b> ${data.editor.progress_text}`
          : `<b>Trạng thái Bộ Cắt & Edit Video Mới:</b> ${data.editor.progress_text}`;
      }
    }

    if (data.bridge) {
      const brBox = document.getElementById('bridge-detail');
      if (brBox) {
        const stBadge = data.bridge.r630_remote_reachable
          ? `<span class="badge b-ok">✓ ĐÃ NỐI THÔNG VỀ SERVER NHÀ</span>`
          : `<span class="badge b-warn">ĐANG Ở NGOÀI MẠNG NHÀ (CHƯA BẬT TUNNEL)</span>`;
        brBox.innerHTML =
          `${stBadge} &nbsp; <b>IP WAN Nhà (Port 4898):</b> <code>${data.bridge.home_wan_ip}</code><br>` +
          `<span style="color:#38bdf8;">${data.bridge.last_bridge_msg}</span>`;
      }
    }

    const btnSched = document.getElementById('btn-toggle-sched');
    if (currentSettings.auto_scheduler_enabled) {
      btnSched.textContent = '⏸️ Tắt Nhắc Tự Động (Đang bật 1 Tiếng / Video)';
      btnSched.className = 'btn btn-dark';
    } else {
      btnSched.textContent = '⏰ Bật Nhắc Lịch 1 Tiếng / Video';
      btnSched.className = 'btn btn-green';
    }

    const qt = document.getElementById('queue-tbody');
    if (data.ready_queue && data.ready_queue.length > 0) {
      queueMap = {};
      qt.innerHTML = data.ready_queue.map((item, idx) => {
        queueMap[item.id] = item;
        const fname = (item.output_video || '').split('/').pop();
        const isFirst = idx === 0;
        const isDrafted = item.status === 'SAVED_DRAFT';
        return `
          <tr style="${isFirst ? 'background:rgba(253,224,71,0.06);' : ''}">
            <td>
              <div style="font-weight:800; color:${isFirst ? '#4ade80' : 'var(--blue)'}; margin-bottom:4px;">
                ${isFirst ? '🔔 ' : '🕒 '}${item.scheduled_1h_slot}
              </div>
              <div style="font-size:15px; font-weight:800; color:var(--accent);">${item.channel}</div>
              <div style="margin-top:6px;">
                ${isDrafted
                  ? `<span class="badge b-draft">📝 ĐÃ LƯU NHÁP TRÊN OPPO A57 (${item.drafted_at || ''})</span>`
                  : (item.cached_offline ? '<span class="badge b-ok">✓ Sẵn sàng trong ổ C:</span>' : '<span class="badge b-warn">Chờ tải</span>')}
              </div>
            </td>
            <td>
              <b>${item.product_name}</b><br><br>
              <span class="mono">Shop GMV Max ID:<br>${item.seller_id}</span><br>
              <span style="font-size:11px; color:var(--muted);">File: ${fname}</span>
            </td>
            <td>
              <div class="cap-card">${item.caption_seo}</div>
            </td>
            <td>
              <div style="display:flex; flex-direction:column; gap:8px;">
                ${isDrafted
                  ? `<button class="btn btn-dark" disabled style="opacity:0.65; cursor:not-allowed; border:1px solid #eab308; color:#fde047;">
                       🔒 Đã Khóa Nạp Lại (Đã Lưu Nháp - Chống Trùng 100%)
                     </button>`
                  : `<button class="btn btn-yellow" onclick="saveDraftOnOppo('${item.id}')">
                       📝 1. Tự Động Đẩy Video + Dán Tiếng Việt & Lưu Nháp
                     </button>`}
                <button class="btn btn-green" onclick="markPosted('${item.id}')">
                  ✅ 2. Đánh Dấu Đã Đăng Từ Nháp (Khóa & Xóa Video Gốc)
                </button>
                <button class="btn btn-blue" id="cpbtn-${item.id}" onclick="copyCap('${item.id}')">
                  📋 Copy Caption Tiếng Việt Có Dấu
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    } else {
      qt.innerHTML = '<tr><td colspan="4" style="color:var(--muted);">Không còn video nào trong hàng chờ.</td></tr>';
    }

    const lt = document.getElementById('ledger-tbody');
    if (data.ledger && data.ledger.length > 0) {
      lt.innerHTML = data.ledger.map(row => `
        <tr>
          <td><b>${row.posted_at}</b></td>
          <td><b style="color:var(--accent);">${row.channel}</b></td>
          <td><code>${row.clip_id}</code></td>
          <td>${row.product_name}</td>
          <td class="mono">${(row.file_sha256 || '').slice(0, 18)}...</td>
          <td><span class="badge b-ok">✅ ĐÃ ĐĂNG & KHÓA CHỐNG TRÙNG</span></td>
        </tr>
      `).join('');
    } else {
      lt.innerHTML = '<tr><td colspan="6" style="color:var(--muted);">Chưa có video nào được đánh dấu đã đăng.</td></tr>';
    }
  } catch (e) {}
}

async function apiPost(url, payload) {
  document.getElementById('last-msg').textContent = 'Đang thực thi lệnh trên Oppo A57...';
  const r = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload || {})
  });
  const res = await r.json();
  await refreshStatus();
  return res;
}

function copyCap(itemId) {
  const item = queueMap[itemId];
  if (!item) return;
  navigator.clipboard.writeText(item.caption_seo);
  const btn = document.getElementById('cpbtn-' + itemId);
  if (btn) {
    btn.textContent = '✓ Đã Copy Caption Tiếng Việt Có Dấu!';
    setTimeout(() => { btn.textContent = '📋 Copy Caption Tiếng Việt Có Dấu'; }, 3000);
  }
}

function connectOppo(ipPort) { apiPost('/api/connect_oppo', {ip_port: ipPort}); }
function pairOppo() {
  apiPost('/api/pair_oppo', {
    pair_ip_port: document.getElementById('pair-ip').value,
    pair_code: document.getElementById('pair-code').value,
    main_ip_port: document.getElementById('pair-main-port').value
  });
}
function syncR630() { apiPost('/api/sync_r630', {}); }
function testSwitch(ch) { apiPost('/api/test_switch', {channel: ch}); }
function saveDraftOnOppo(itemId) { apiPost('/api/save_draft_on_oppo', {item_id: itemId}); }
function markPosted(itemId) { apiPost('/api/mark_posted', {item_id: itemId}); }
function triggerReminderNow() { apiPost('/api/trigger_reminder_now', {}); }
function masterCtrl(target, action) { apiPost('/api/master_control', {target: target, action: action}); }
function startRemoteBridge(wanIpPort) { apiPost('/api/start_remote_bridge', {wan_ip_port: wanIpPort || ''}); }
function startFetchEditNewLink() {
  apiPost('/api/fetch_edit_new_link', {
    livevault_url: document.getElementById('new-lv-url').value,
    max_clips: parseInt(document.getElementById('new-lv-count').value || '5', 10),
    product_key: document.getElementById('new-lv-prod').value
  });
}
function toggleScheduler() {
  apiPost('/api/update_settings', {auto_scheduler_enabled: !currentSettings.auto_scheduler_enabled});
}

refreshStatus();
setInterval(refreshStatus, 6000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    cfg = get_settings()
    cfg["auto_scheduler_enabled"] = True
    SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print(" TIKTOK AUTOHUB - AUTO-SAVE-DRAFT (VIETNAMESE) & 1H POST REMINDER")
    print(f" Giao dien Laptop: http://127.0.0.1:{PORT}")
    print("=" * 72)
    t = threading.Thread(target=background_scheduler_loop, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), LaptopHubHandler)
    server.serve_forever()
