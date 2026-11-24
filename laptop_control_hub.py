# -*- coding: utf-8 -*-
"""
TIKTOK AUTOHUB - STANDALONE LAPTOP CONTROL CENTER, 1-HOUR REMINDER & OPPO A57 HELPER
Theo dung luong nguoi dung yeu cau:
1. He thong TU DONG chuan bi Video da cat + Caption Tieng Viet CO DAU 100% + Len lich gian cach 1 Tieng / 1 Video.
2. Moi 1 TIENG (60 phut), he thong TU DONG NHAC NGUOI DUNG DANG BAI:
   - Phat chuong + Hien bang nhac tren man hinh Windows Laptop
   - Tu dong day DUY NHAT 1 video cua khung gio do sang cuon Camera Oppo A57 & Mo san the Copy Caption Tieng Viet CO DAU tren Oppo A57.
3. Nguoi dung tu lam buoc cuoi tren TikTok (Chon video #1 -> Dan Caption Tieng Viet co dau -> Gan gio hang -> Bam Dang),
   sau do bam nut '[✅ Đánh Dấu Đã Đăng]' (tren Oppo A57 hoac tren Laptop) de he thong:
   - Khoa ma SHA-256 cua video vao So cai Chong Dang Trung 3 Lop
   - Gach bai do khoi danh sach cho & Bat dau dem nguoc 60 phut (1 tieng) cho luot nhac tiep theo!
"""
import ctypes
import json
import subprocess
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
    ensure_correct_tiktok_account,
    get_laptop_lan_ip,
    mark_video_as_posted,
    pair_oppo_wireless,
    quick_check_oppo_connected,
    send_video_and_vietnamese_card_to_oppo,
)

PORT = 8099
RUNTIME_STATE = {
    "last_action_time": datetime.now().strftime("%H:%M:%S"),
    "last_action_result": "Sẵn sàng: Lên lịch 1 tiếng/video • Caption Tiếng Việt có dấu 100% • Nhắc đăng & Đánh dấu đã đăng",
    "next_reminder_epoch": time.time() + 3600,
    "reminder_active_alert": False,
    "current_due_item": None,
    "r630_sync_status": {"r630_online": False, "cached_offline_ready": 0, "total_queue": 0},
    "oppo_status": {"connected": False, "serial": None, "mode": "NONE", "detail": "Đang kiểm tra..."},
}


def popup_windows_reminder(title: str, message: str):
    """Phat am thanh chuong nhac & hien Hop thoai Nhac Dang Bai tren man hinh Laptop Windows (khong chan luong)."""
    def _alert():
        try:
            import winsound
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                time.sleep(0.35)
        except Exception:
            pass
        try:
            # MB_OK | MB_ICONINFORMATION | MB_SYSTEMMODAL (0x00001040) -> Noi len tren cung man hinh Laptop
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x00001040)
        except Exception:
            pass

    threading.Thread(target=_alert, daemon=True).start()


def get_ready_queue_with_1h_schedule() -> list[dict]:
    """
    Lay danh sach cac video READY va gan khung gio len lich gian cach dung 1 TIENG / 1 VIDEO (60 phut)
    luan phien giua @suckhoeviet.2 va @suc.khoe.vang.268.
    """
    if not LOCAL_QUEUE_FILE.exists():
        return []
    try:
        raw = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    ch1 = [x for x in raw if x.get("status") != "POSTED" and x.get("channel") == "@suckhoeviet.2"]
    ch2 = [x for x in raw if x.get("status") != "POSTED" and x.get("channel") == "@suc.khoe.vang.268"]

    # Tron luan phien 1 bai @suckhoeviet.2 -> 1 bai @suc.khoe.vang.268 cach nhau 1 tieng
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
            "Ngay bây giờ (Đến giờ đăng)" if idx == 0 else slot_dt.strftime("%H:%M · %d/%m/%Y (Cách %dh)" % idx)
        )
        fname = Path(item.get("output_video", "")).name
        item["cached_offline"] = (CACHE_DIR / fname).exists()
    return interleaved


def trigger_1hour_reminder_now() -> dict:
    """Kich hoat nhac dang bai 1 tieng: Day san video #1 sang Oppo A57 + Mo the Copy Caption Tieng Viet + Hien Popup Laptop."""
    ready = get_ready_queue_with_1h_schedule()
    if not ready:
        return {"ok": False, "message": "Không còn video nào trong hàng chờ cần nhắc."}

    due_item = ready[0]
    RUNTIME_STATE["current_due_item"] = due_item
    RUNTIME_STATE["reminder_active_alert"] = True

    res = send_video_and_vietnamese_card_to_oppo(item_id=due_item["id"], switch_account=True)
    RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
    RUNTIME_STATE["last_action_result"] = f"🔔 ĐẾN GIỜ ĐĂNG (1 Tiếng/Video): {res.get('message', '')}"

    popup_windows_reminder(
        "⏰ ĐẾN GIỜ ĐĂNG VIDEO TIKTOK (GIÃN CÁCH 1 TIẾNG / 1 VIDEO)",
        f"Đã đến giờ đăng bài tiếp theo!\n\n"
        f"• Tài khoản: {due_item['channel']}\n"
        f"• Sản phẩm: {due_item['product_name']}\n"
        f"• Shop GMV Max ID: {due_item['seller_id']}\n\n"
        f"Hệ thống đã:\n"
        f"1) Copy sẵn Caption Tiếng Việt CÓ DẤU vào Clipboard.\n"
        f"2) Đẩy duy nhất video này vào đầu cuộn Camera Oppo A57 & mở sẵn thẻ Copy Caption Tiếng Việt trên điện thoại.\n\n"
        f"👉 Sau khi bạn tự đăng xong trên Oppo A57, hãy bấm nút [✅ Đánh Dấu Đã Đăng] để hệ thống khóa chống trùng và hẹn nhắc 1 tiếng tiếp theo!",
    )
    return res


def background_scheduler_loop():
    """Luong chay ngam: Dong bo kho video Offline tu R630 & Dem nguoc nhac dang bai moi 60 phut (1 tieng)."""
    init_db()
    last_sync_ts = 0.0
    while True:
        try:
            now = time.time()
            if now - last_sync_ts >= 120:
                RUNTIME_STATE["r630_sync_status"] = sync_from_r630_to_laptop_cache()
                last_sync_ts = now

            cfg = get_settings()
            if cfg.get("auto_scheduler_enabled", True):
                if now >= RUNTIME_STATE["next_reminder_epoch"]:
                    trigger_1hour_reminder_now()
                    interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
                    RUNTIME_STATE["next_reminder_epoch"] = time.time() + interval_sec
        except Exception as e:
            RUNTIME_STATE["last_action_result"] = f"Lỗi luồng nền: {e}"
        time.sleep(10)


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
            return self._send_json({
                "settings": cfg,
                "lan_ip": get_laptop_lan_ip(),
                "runtime": RUNTIME_STATE,
                "next_wait_seconds": rem_sec,
                "ledger": ledger,
                "ready_queue": ready_queue[:24],
            })

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
            html = self._build_mobile_oppo_card_html(item_id)
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
            res = pair_oppo_wireless(body.get("pair_ip_port", ""), body.get("pair_code", ""))
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            return self._send_json(res)

        if parsed.path == "/api/sync_r630":
            res = sync_from_r630_to_laptop_cache()
            RUNTIME_STATE["r630_sync_status"] = res
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = (
                f"Đã đồng bộ kho video từ R630: {res['cached_offline_ready']} video đã lưu sẵn trong ổ C: Laptop."
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

        if parsed.path == "/api/prepare_on_oppo":
            item_id = body.get("item_id") or None
            ch = body.get("channel") or None
            res = send_video_and_vietnamese_card_to_oppo(item_id=item_id, channel=ch, switch_account=True)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            return self._send_json(res)

        if parsed.path == "/api/mark_posted":
            item_id = body.get("item_id", "")
            res = mark_video_as_posted(item_id)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            if res.get("ok"):
                # Reset bo dem nguoc 60 phut (1 tieng) ke tu luc nguoi dung danh dau da dang!
                cfg = get_settings()
                interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
                RUNTIME_STATE["next_reminder_epoch"] = time.time() + interval_sec
                RUNTIME_STATE["reminder_active_alert"] = False
            return self._send_json(res)

        if parsed.path == "/api/update_caption":
            item_id = body.get("item_id", "")
            new_cap = (body.get("caption_seo") or "").strip()
            if LOCAL_QUEUE_FILE.exists() and item_id and new_cap:
                q = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
                for x in q:
                    if x.get("id") == item_id:
                        x["caption_seo"] = new_cap
                        break
                LOCAL_QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
                return self._send_json({"ok": True, "message": "Đã lưu Caption Tiếng Việt mới!"})
            return self._send_json({"ok": False, "message": "Dữ liệu không hợp lệ"})

        if parsed.path == "/api/trigger_reminder_now":
            res = trigger_1hour_reminder_now()
            return self._send_json(res)

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
                f"Đã cập nhật bộ nhắc đăng 1 tiếng/video: {'ĐANG BẬT' if cfg['auto_scheduler_enabled'] else 'ĐANG TẮT'}"
            )
            return self._send_json({"ok": True, "settings": cfg})

        self.send_error(404)

    def _build_mobile_oppo_card_html(self, item_id: str) -> str:
        """Giao dien tinh gon mo truc tiep tren man hinh Oppo A57: 1 cham Copy Caption Tieng Viet Co Dau & Danh Dau Da Dang."""
        ready = get_ready_queue_with_1h_schedule()
        item = next((x for x in ready if x.get("id") == item_id), ready[0] if ready else None)
        if not item:
            return "<h2 style='color:white;background:#0b0f19;padding:20px;font-family:sans-serif;'>Đã đăng hết toàn bộ video trong hàng chờ!</h2>"

        fname = Path(item.get("output_video", "")).name
        cap_json = json.dumps(item["caption_seo"], ensure_ascii=False)
        return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oppo A57 — Copy Caption Tiếng Việt & Đăng TikTok</title>
<style>
  body {{ margin:0; padding:16px; background:#0b0f19; color:#f8fafc; font-family:'Segoe UI',system-ui,sans-serif; }}
  .card {{ background:#131b2e; border:2px solid #fde047; border-radius:16px; padding:18px; max-width:520px; margin:0 auto; }}
  .ch {{ font-size:20px; font-weight:800; color:#fde047; margin-bottom:6px; }}
  .sub {{ font-size:13px; color:#94a3b8; margin-bottom:12px; }}
  .cap-box {{ background:#090d16; border:1px solid #334155; border-radius:12px; padding:14px;
              font-size:15px; line-height:1.55; white-space:pre-line; color:#fff; margin-bottom:14px; }}
  .btn {{ width:100%; border:none; border-radius:12px; padding:15px; font-size:16px; font-weight:800;
          cursor:pointer; margin-bottom:10px; display:block; text-align:center; text-decoration:none; }}
  .btn-yellow {{ background:#fde047; color:#000; }}
  .btn-green {{ background:#22c55e; color:#052e16; }}
  .btn-blue {{ background:#38bdf8; color:#082f49; }}
</style>
</head>
<body>
<div class="card">
  <div class="ch">🎯 Kênh đăng: {item['channel']}</div>
  <div class="sub">
    <b>Sản phẩm gắn giỏ:</b> {item['product_name']}<br>
    <b>Shop GMV Max ID:</b> <code>{item['seller_id']}</code><br>
    <b>File video (đã nằm ở vị trí #1 trong Camera):</b> <code>{fname}</code>
  </div>

  <div style="font-size:13px; color:#fde047; font-weight:700; margin-bottom:6px;">
    📝 CAPTION TIẾNG VIỆT CÓ DẤU + 5 HASHTAG CHUẨN SEO:
  </div>
  <div class="cap-box" id="vn-cap">{item['caption_seo']}</div>

  <button class="btn btn-yellow" id="btn-copy" onclick="copyVietnameseCaption()">
    📋 BƯỚC 1: CHẠM ĐỂ COPY CAPTION TIẾNG VIỆT CÓ DẤU
  </button>

  <button class="btn btn-green" id="btn-done" onclick="markPosted('{item['id']}')">
    ✅ BƯỚC 2: ĐÁNH DẤU ĐÃ ĐĂNG (KHÓA CHỐNG TRÙNG & HẸN 1 TIẾNG SAU)
  </button>

  <a class="btn btn-blue" href="/video?file={urllib.parse.quote(fname)}">
    ⬇️ Tải lại file Video .MP4 (Nếu cần)
  </a>
</div>

<script>
const CAPTION_TEXT = {cap_json};
function copyVietnameseCaption() {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(CAPTION_TEXT);
  }} else {{
    const ta = document.createElement('textarea');
    ta.value = CAPTION_TEXT;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }}
  const b = document.getElementById('btn-copy');
  b.textContent = '✓ ĐÃ COPY CAPTION TIẾNG VIỆT CÓ DẤU! HÃY DÁN VÀO TIKTOK';
  b.style.background = '#4ade80';
}}

async function markPosted(itemId) {{
  const b = document.getElementById('btn-done');
  b.textContent = 'Đang khóa Sổ cái chống trùng...';
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
<title>TikTok AutoHub — Lịch Đăng 1 Tiếng/Video & Caption Tiếng Việt Có Dấu</title>
<style>
  :root {
    --bg: #0b0f19; --card: #131b2e; --border: #26324d;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #fde047;
    --green: #22c55e; --red: #ef4444; --blue: #38bdf8;
  }
  * { box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { margin: 0; padding: 20px; background: var(--bg); color: var(--text); }
  .wrap { max-width: 1340px; margin: 0 auto; }
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
  .timer-box { font-size: 24px; font-weight: 800; color: #4ade80; margin: 8px 0; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
  th, td { text-align: left; padding: 12px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  .mono { font-family: Consolas, monospace; font-size: 12px; color: #38bdf8; }
  .cap-card { background: #090d16; border: 1px solid #26324d; border-radius: 10px; padding: 10px 12px;
              white-space: pre-line; font-size: 13px; line-height: 1.5; color: #f8fafc; min-width: 360px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <div class="title">⚡ TIKTOK AUTOHUB — QUẢN LÝ VIDEO, CAPTION TIẾNG VIỆT & NHẮC LỊCH 1 TIẾNG / VIDEO</div>
      <div class="sub">Hệ thống tự cắt video, chuẩn bị Caption Tiếng Việt có dấu 100%, nhắc bạn đăng mỗi 1 tiếng và đánh dấu khóa chống trùng</div>
    </div>
    <div id="top-badges" class="row"></div>
  </div>

  <div class="log-bar">
    <strong>Trạng thái mới nhất:</strong> <span id="last-msg">Đang tải...</span>
  </div>

  <div class="grid">
    <!-- CARD 1: BO DEM NGUOC NHAC DANG MOI 1 TIENG -->
    <div class="card">
      <h3>⏰ 1. Bộ Nhắc Đăng Video Mỗi 1 Tiếng (60 Phút / Video)</h3>
      <div style="font-size:13px; color:var(--muted);">
        Cứ mỗi 60 phút (hoặc sau khi bạn bấm <b>✅ Đánh Dấu Đã Đăng</b> đúng 1 tiếng), Laptop sẽ đổ chuông + bật bảng nhắc và đẩy sẵn video tiếp theo sang Camera Oppo A57:
      </div>
      <div class="timer-box" id="countdown-timer">⏳ Đang tính thời gian...</div>
      <div class="row">
        <button id="btn-toggle-sched" class="btn btn-green" onclick="toggleScheduler()">⏰ Bật Nhắc Lịch 1 Tiếng / Video</button>
        <button class="btn btn-yellow" onclick="triggerReminderNow()">🔔 Nhắc & Đẩy Bài Tiếp Theo Ngay</button>
      </div>
    </div>

    <!-- CARD 2: KET NOI OPPO A57 & MO THE COPY TREN DIEN THOAI -->
    <div class="card">
      <h3>📱 2. Kết Nối Oppo A57 & Trang Copy Tiếng Việt Trên Điện Thoại</h3>
      <div id="oppo-detail" style="font-size:13px; color:var(--muted); margin-bottom:8px;">Đang kiểm tra...</div>
      <div id="mobile-url-box" style="font-size:13px; background:#090d16; padding:8px 10px; border-radius:8px; border:1px solid var(--border);"></div>
      <div class="row">
        <button class="btn btn-yellow" onclick="connectOppo('')">🔌 Tự Động Tìm & Nối Oppo A57</button>
        <button class="btn btn-dark" onclick="testSwitch('@suckhoeviet.2')">🔄 Chuyển sang @suckhoeviet.2</button>
        <button class="btn btn-dark" onclick="testSwitch('@suc.khoe.vang.268')">🔄 Chuyển sang @suc.khoe.vang.268</button>
      </div>
    </div>

    <!-- CARD 3: KHO VIDEO OFFLINE TREN LAPTOP -->
    <div class="card">
      <h3>📦 3. Kho Video Đã Lưu Sẵn Trên Laptop (Đi Ra Ngoài)</h3>
      <div id="cache-detail" style="font-size:13px; color:var(--muted); margin-bottom:10px;">Đang kiểm tra...</div>
      <div class="row">
        <button class="btn btn-blue" onclick="syncR630()">📥 Đồng Bộ Video Mới Từ R630 Về Laptop</button>
      </div>
      <div style="font-size:12px; color:var(--muted); margin-top:10px; line-height:1.5;">
        • Khi bấm <b>📲 Đẩy Video Sang Oppo A57</b> ở bảng dưới, hệ thống sẽ xóa video cũ trong Camera điện thoại, chỉ để lại <b>duy nhất 1 video</b> ở vị trí #1 và mở sẵn thẻ Copy Caption Tiếng Việt có dấu trên Oppo A57.
      </div>
    </div>
  </div>

  <!-- BANG LICH DANG 1 TIENG / 1 VIDEO + CAPTION TIENG VIET CO DAU + NUT DANH DAU DA DANG -->
  <div class="card" style="margin-bottom:18px;">
    <h3>📅 Lịch Đăng Video Giãn Cách 1 Tiếng / 1 Bài (Caption Tiếng Việt Có Dấu 100% & Đánh Dấu Đã Đăng)</h3>
    <table>
      <thead>
        <tr>
          <th style="width:170px;">Khung Giờ (Cách 1h) & Kênh</th>
          <th style="width:240px;">Sản Phẩm & Shop GMV Max</th>
          <th>Caption Tiếng Việt Có Dấu + 5 Hashtag Chuẩn SEO</th>
          <th style="width:290px;">Thao Tác Chuẩn Bị & Đánh Dấu Đã Đăng</th>
        </tr>
      </thead>
      <tbody id="queue-tbody"></tbody>
    </table>
  </div>

  <!-- BANG SO CAI CHONG DANG TRUNG 3 LOP (CAC VIDEO DA DANH DAU DANG) -->
  <div class="card">
    <h3>🛡️ Lịch Sử Các Video Bạn Đã Đánh Dấu Đăng (Đã Khóa Chống Trùng SHA-256)</h3>
    <table>
      <thead>
        <tr>
          <th>Thời gian đánh dấu</th>
          <th>Tài khoản</th>
          <th>Clip Gốc</th>
          <th>Sản phẩm</th>
          <th>Mã Băm Video (SHA-256)</th>
          <th>Trạng thái</th>
        </tr>
      </thead>
      <tbody id="ledger-tbody">
        <tr><td colspan="6" style="color:var(--muted);">Chưa có video nào được đánh dấu đã đăng.</td></tr>
      </tbody>
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
      ? `⏳ Nhắc bài tiếp theo sau: ${formatMMSS(remainingSeconds)}`
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

    document.getElementById('mobile-url-box').innerHTML =
      `🌐 Trang mở trên trình duyệt Oppo A57 (cùng Wi-Fi): <a href="http://${data.lan_ip}:8099/mobile" target="_blank" style="color:var(--accent);font-weight:700;">http://${data.lan_ip}:8099/mobile</a>`;

    const badges = [];
    if (oppo.connected) {
      badges.push(`<span class="badge b-ok">📱 Oppo A57: ĐÃ KẾT NỐI (${oppo.mode})</span>`);
    } else {
      badges.push(`<span class="badge b-warn">📱 Oppo A57: CHƯA KẾT NỐI</span>`);
    }
    badges.push(`<span class="badge b-info">📦 Kho Offline Laptop: ${r630.cached_offline_ready || 0} Video sẵn sàng</span>`);
    badges.push(`<span class="badge b-ok">🛡️ Đã Đăng & Khóa Chống Trùng: ${(data.ledger || []).length} Video</span>`);
    document.getElementById('top-badges').innerHTML = badges.join('');

    document.getElementById('oppo-detail').innerHTML = oppo.connected
      ? `<span style="color:#4ade80;font-weight:700;">✓ Đã kết nối Oppo A57 (${oppo.serial})</span>`
      : `<span>${oppo.detail || 'Chưa kết nối'}</span>`;

    document.getElementById('cache-detail').innerHTML =
      `Kho video Offline trên Laptop (<code>C:\\TikTok_AutoHub\\video_cache</code>): <b>${r630.cached_offline_ready || 0}</b> video đã tải sẵn / <b>${r630.total_queue || 0}</b> bài chờ đăng.`;

    const btnSched = document.getElementById('btn-toggle-sched');
    if (currentSettings.auto_scheduler_enabled) {
      btnSched.textContent = '⏸️ Tắt Nhắc Tự Động (Đang bật 1 Tiếng / Video)';
      btnSched.className = 'btn btn-dark';
    } else {
      btnSched.textContent = '⏰ Bật Nhắc Lịch 1 Tiếng / Video';
      btnSched.className = 'btn btn-green';
    }

    // Render Queue
    const qt = document.getElementById('queue-tbody');
    if (data.ready_queue && data.ready_queue.length > 0) {
      queueMap = {};
      qt.innerHTML = data.ready_queue.map((item, idx) => {
        queueMap[item.id] = item;
        const fname = (item.output_video || '').split('/').pop();
        const isFirst = idx === 0;
        return `
          <tr style="${isFirst ? 'background:rgba(253,224,71,0.06);' : ''}">
            <td>
              <div style="font-weight:800; color:${isFirst ? '#4ade80' : 'var(--blue)'}; margin-bottom:4px;">
                ${isFirst ? '🔔 ' : '🕒 '}${item.scheduled_1h_slot}
              </div>
              <div style="font-size:15px; font-weight:800; color:var(--accent);">${item.channel}</div>
              <div style="margin-top:6px;">
                ${item.cached_offline ? '<span class="badge b-ok">✓ Đã lưu ổ C:</span>' : '<span class="badge b-warn">Chờ tải</span>'}
              </div>
            </td>
            <td>
              <b>${item.product_name}</b><br><br>
              <span class="mono">Shop GMV Max ID:<br>${item.seller_id}</span><br>
              <span style="font-size:11px; color:var(--muted);">File: ${fname}</span>
            </td>
            <td>
              <div class="cap-card" id="cap-${item.id}">${item.caption_seo}</div>
            </td>
            <td>
              <div style="display:flex; flex-direction:column; gap:8px;">
                <button class="btn btn-yellow" onclick="prepareOnOppo('${item.id}')">
                  📲 1. Đẩy Video + Mở Thẻ Copy Trên Oppo A57
                </button>
                <button class="btn btn-blue" id="cpbtn-${item.id}" onclick="copyCap('${item.id}')">
                  📋 Copy Caption Tiếng Việt Có Dấu
                </button>
                <button class="btn btn-green" onclick="markPosted('${item.id}')">
                  ✅ 2. Đánh Dấu Đã Đăng (Khóa Chống Trùng)
                </button>
                <a class="btn btn-dark" href="/video?file=${encodeURIComponent(fname)}" target="_blank">
                  👁️ Xem / Tải File Video (.MP4)
                </a>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    } else {
      qt.innerHTML = '<tr><td colspan="4" style="color:var(--muted);">Không còn video nào trong hàng chờ.</td></tr>';
    }

    // Render Ledger
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
  document.getElementById('last-msg').textContent = 'Đang thực thi...';
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
function syncR630() { apiPost('/api/sync_r630', {}); }
function testSwitch(ch) { apiPost('/api/test_switch', {channel: ch}); }
function prepareOnOppo(itemId) { apiPost('/api/prepare_on_oppo', {item_id: itemId}); }
function markPosted(itemId) { apiPost('/api/mark_posted', {item_id: itemId}); }
function triggerReminderNow() { apiPost('/api/trigger_reminder_now', {}); }
function toggleScheduler() {
  apiPost('/api/update_settings', {auto_scheduler_enabled: !currentSettings.auto_scheduler_enabled});
}

refreshStatus();
setInterval(refreshStatus, 8000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    cfg = get_settings()
    cfg["auto_scheduler_enabled"] = True
    SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print(" TIKTOK AUTOHUB - VIETNAMESE CAPTION, 1H REMINDER & MANUAL MARK POSTED")
    print(f" Giao dien Laptop: http://127.0.0.1:{PORT}")
    print(f" Giao dien Mobile Oppo A57: http://{get_laptop_lan_ip()}:{PORT}/mobile")
    print("=" * 72)
    t = threading.Thread(target=background_scheduler_loop, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), LaptopHubHandler)
    server.serve_forever()
