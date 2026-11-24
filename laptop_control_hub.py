# -*- coding: utf-8 -*-
"""
TIKTOK AUTOHUB - STANDALONE LAPTOP CONTROL CENTER & 1-HOUR SCHEDULER
Chay doc lap tren Laptop cua ban tai: http://localhost:8099 (Khong can mo AI Chat, khong phu thuoc R630 khi mang ra ngoai!)
Chuc nang chinh:
1. Tu dong Pre-cache (tai truoc) video da render tu Server R630 (192.168.1.240:8088) ve C:\\TikTok_AutoHub\\video_cache\\ khi o nha.
2. Khi mang Laptop + Oppo A57 ra ngoai (khac mang voi R630), he thong tu chuyen sang che do OFFLINE CACHE va tu tim Oppo A57 trong mang Wi-Fi/Hotspot moi.
3. Bo lap lich (Scheduler) chay ngam: Tu dong dang gian cach dung 1 TIENG / 1 VIDEO (60 phut) luan phien giua @suckhoeviet.2 va @suc.khoe.vang.268.
4. Kiem soat Chong Dang Trung 3 Lop (SQLite SHA-256 file + clip_id + caption).
"""
import json
import os
import threading
import time
import urllib.parse
from datetime import datetime
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
    execute_tiktok_post_flow,
    pair_oppo_wireless,
    quick_check_oppo_connected,
)

PORT = 8099
RUNTIME_STATE = {
    "last_action_time": "Chưa chạy",
    "last_action_result": "Sẵn sàng điều khiển Oppo A57 (@suckhoeviet.2 & @suc.khoe.vang.268)",
    "last_post_epoch": 0.0,
    "next_channel_idx": 0,
    "r630_sync_status": {"r630_online": False, "cached_offline_ready": 0, "total_queue": 0},
    "oppo_status": {"connected": False, "serial": None, "mode": "NONE", "detail": "Đang kiểm tra..."},
}


def background_scheduler_loop():
    """Luong chay ngam 24/7 tren Laptop: Dong bo Cache tu R630 + Tu dong dang 1 tieng / 1 video."""
    init_db()
    last_sync_ts = 0.0
    while True:
        try:
            now = time.time()
            # 1. Moi 120 giay thu dong bo kho video tu R630 ve Cache Laptop (neu o cung mang voi R630)
            if now - last_sync_ts >= 120:
                RUNTIME_STATE["r630_sync_status"] = sync_from_r630_to_laptop_cache()
                last_sync_ts = now

            # 2. Kiem tra bo lap lich tu dong dang 1 tieng (60 phut) / 1 video
            cfg = get_settings()
            interval_sec = max(15, int(cfg.get("interval_minutes", 60))) * 60
            if cfg.get("auto_scheduler_enabled", False):
                elapsed = now - RUNTIME_STATE["last_post_epoch"]
                if elapsed >= interval_sec:
                    ch_list = cfg.get("active_channels") or ALLOWED_CHANNELS
                    target_ch = ch_list[RUNTIME_STATE["next_channel_idx"] % len(ch_list)]
                    res = execute_tiktok_post_flow(channel=target_ch, dry_run_switch_only=False)
                    RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
                    RUNTIME_STATE["last_action_result"] = f"[Auto-1h {target_ch}] {res.get('message', '')}"
                    if res.get("ok"):
                        RUNTIME_STATE["last_post_epoch"] = time.time()
                        RUNTIME_STATE["next_channel_idx"] = (RUNTIME_STATE["next_channel_idx"] + 1) % len(ch_list)
        except Exception as e:
            RUNTIME_STATE["last_action_result"] = f"Lỗi luồng nền: {e}"
        time.sleep(15)


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
            ledger = get_ledger_history(25)
            queue = []
            if LOCAL_QUEUE_FILE.exists():
                try:
                    queue = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    queue = []
            ready_queue = [x for x in queue if x.get("status") != "POSTED" and x.get("channel") in ALLOWED_CHANNELS]
            cached_count = sum(1 for x in ready_queue if (CACHE_DIR / Path(x.get("output_video", "")).name).exists())
            RUNTIME_STATE["r630_sync_status"]["cached_offline_ready"] = cached_count
            RUNTIME_STATE["r630_sync_status"]["total_queue"] = len(ready_queue)

            next_wait_sec = 0
            if cfg.get("auto_scheduler_enabled") and RUNTIME_STATE["last_post_epoch"] > 0:
                rem = int(cfg.get("interval_minutes", 60) * 60 - (time.time() - RUNTIME_STATE["last_post_epoch"]))
                next_wait_sec = max(0, rem)

            return self._send_json({
                "settings": cfg,
                "runtime": RUNTIME_STATE,
                "next_wait_seconds": next_wait_sec,
                "ledger": ledger,
                "ready_queue": ready_queue[:20],
            })

        if parsed.path == "/video":
            fname = Path(qs.get("file", [""])[0]).name
            fpath = CACHE_DIR / fname
            if fpath.exists():
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, "Video not cached locally")
            return

        # Render Dark Mode Control Center UI
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
            ip_port = body.get("pair_ip_port", "")
            code = body.get("pair_code", "")
            res = pair_oppo_wireless(ip_port, code)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            return self._send_json(res)

        if parsed.path == "/api/sync_r630":
            res = sync_from_r630_to_laptop_cache()
            RUNTIME_STATE["r630_sync_status"] = res
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = (
                f"Đã đồng bộ kho video từ R630: {res['cached_offline_ready']} video đã lưu sẵn trong ổ C: Laptop (tải mới {res['downloaded_now']} video)."
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

        if parsed.path == "/api/post_now":
            ch = body.get("channel") or None
            res = execute_tiktok_post_flow(channel=ch, dry_run_switch_only=False)
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = res.get("message", "")
            if res.get("ok"):
                RUNTIME_STATE["last_post_epoch"] = time.time()
            return self._send_json(res)

        if parsed.path == "/api/update_settings":
            cfg = get_settings()
            for k in ("auto_scheduler_enabled", "interval_minutes", "post_mode", "r630_url", "oppo_last_ip"):
                if k in body:
                    cfg[k] = body[k]
            SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            RUNTIME_STATE["last_action_time"] = datetime.now().strftime("%H:%M:%S")
            RUNTIME_STATE["last_action_result"] = (
                f"Đã lưu cài đặt: Tự động 1 tiếng/video = {'BẬT' if cfg['auto_scheduler_enabled'] else 'TẮT'}, Chế độ = {cfg['post_mode']}"
            )
            return self._send_json({"ok": True, "settings": cfg})

        self.send_error(404)

    def _build_dashboard_html(self) -> str:
        return """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TikTok AutoHub — Laptop + Oppo A57 Standalone Controller</title>
<style>
  :root {
    --bg: #0b0f19; --card: #131b2e; --border: #26324d;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #fde047;
    --green: #22c55e; --red: #ef4444; --blue: #38bdf8;
  }
  * { box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { margin: 0; padding: 20px; background: var(--bg); color: var(--text); }
  .wrap { max-width: 1280px; margin: 0 auto; }
  .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
            background: linear-gradient(135deg, #162038, #0f172a); padding: 18px 22px; border-radius: 14px;
            border: 1px solid var(--border); margin-bottom: 18px; }
  .title { font-size: 21px; font-weight: 800; color: var(--accent); }
  .sub { font-size: 13px; color: var(--muted); margin-top: 4px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; margin-bottom: 18px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
  .card h3 { margin: 0 0 12px 0; font-size: 16px; color: var(--accent); display: flex; align-items: center; gap: 8px; }
  .badge { display: inline-block; padding: 4px 10px; border-radius: 99px; font-size: 12px; font-weight: 700; }
  .b-ok { background: rgba(34,197,94,0.18); color: #4ade80; border: 1px solid #22c55e; }
  .b-warn { background: rgba(239,68,68,0.18); color: #f87171; border: 1px solid #ef4444; }
  .b-info { background: rgba(56,189,248,0.18); color: #38bdf8; border: 1px solid #0284c7; }
  .btn { cursor: pointer; border: none; border-radius: 9px; padding: 10px 14px; font-weight: 700; font-size: 13px;
         transition: 0.15s; display: inline-flex; align-items: center; gap: 6px; }
  .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .btn-yellow { background: var(--accent); color: #000; }
  .btn-green { background: var(--green); color: #052e16; }
  .btn-blue { background: var(--blue); color: #082f49; }
  .btn-dark { background: #1e293b; color: var(--text); border: 1px solid var(--border); }
  input, select { background: #0b1120; border: 1px solid var(--border); color: var(--text);
                  padding: 9px 12px; border-radius: 8px; font-size: 13px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 10px; }
  .log-bar { background: #0f172a; border-left: 4px solid var(--accent); padding: 12px 16px;
             border-radius: 8px; margin-bottom: 18px; font-size: 14px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
  th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  .mono { font-family: Consolas, monospace; font-size: 12px; color: #38bdf8; }
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <div class="title">⚡ TIKTOK AUTOHUB — LAPTOP & OPPO A57 STANDALONE CONTROLLER</div>
      <div class="sub">Chạy độc lập trên Laptop (Không cần mở AI Chat • Hoạt động cả khi mang Laptop + Oppo A57 ra ngoài khác mạng R630)</div>
    </div>
    <div id="top-badges" class="row"></div>
  </div>

  <div class="log-bar" id="action-log">
    <strong>Trạng thái thực thi:</strong> <span id="last-msg">Đang tải trạng thái...</span>
  </div>

  <div class="grid">
    <!-- CARD 1: KET NOI OPPO A57 -->
    <div class="card">
      <h3>📱 1. Kết Nối Oppo A57 (Local Wi-Fi / Hotspot / USB)</h3>
      <div id="oppo-detail" style="font-size:13px; color:var(--muted); margin-bottom:10px;">Đang kiểm tra...</div>
      <div class="row">
        <button class="btn btn-yellow" onclick="connectOppo('')">🔌 Tự Động Tìm & Nối Oppo A57</button>
        <input id="manual-ip" placeholder="Hoặc nhập IP:Port (vd 192.168.1.95:5555)" style="flex:1; min-width:190px;">
        <button class="btn btn-dark" onclick="connectOppo(document.getElementById('manual-ip').value)">Nối IP</button>
      </div>
      <details style="margin-top:12px; font-size:12px; color:var(--muted);">
        <summary style="cursor:pointer; color:var(--blue);">Mẹo kết nối siêu nhanh & Ghép nối mã 6 số (nếu cần)</summary>
        <div style="margin-top:8px; line-height:1.5;">
          • <b>Cách khuyên dùng (Chỉ làm 1 lần):</b> Cắm cáp USB từ Oppo A57 vào Laptop rồi bấm nút Vàng ở trên. Laptop sẽ tự khóa cổng cố định <code>5555</code> trên Oppo A57. Từ đó về sau bạn rút cáp, đi ra quán cafe hay phát Hotspot hệ thống cũng tự quét thấy Oppo A57!<br>
          • Nếu chỉ dùng Gỡ lỗi không dây và đổi Wi-Fi mới cần mã 6 số:
          <div class="row">
            <input id="pair-ip" placeholder="IP:Port ghép nối (vd 192.168.1.95:39123)" style="flex:1;">
            <input id="pair-code" placeholder="Mã 6 số" style="width:95px;">
            <button class="btn btn-blue" onclick="pairOppo()">Ghép nối</button>
          </div>
        </div>
      </details>
    </div>

    <!-- CARD 2: CHUYEN 4 TAI KHOAN & DANG VIDEO -->
    <div class="card">
      <h3>🎯 2. Điều Khiển 4 Tài Khoản & Đăng Video Oppo A57</h3>
      <div style="font-size:13px; color:var(--muted); margin-bottom:10px;">
        Tự động kiểm tra tài khoản đang mở trên TikTok Oppo A57, chuyển đúng về <b>@suckhoeviet.2</b> hoặc <b>@suc.khoe.vang.268</b>, xóa sạch video cũ trong Camera và nạp duy nhất 1 video mới:
      </div>
      <div class="row">
        <button class="btn btn-dark" onclick="testSwitch('@suckhoeviet.2')">🔄 Test Chuyển @suckhoeviet.2</button>
        <button class="btn btn-dark" onclick="testSwitch('@suc.khoe.vang.268')">🔄 Test Chuyển @suc.khoe.vang.268</button>
      </div>
      <div class="row" style="margin-top:12px;">
        <button class="btn btn-green" onclick="postNow('@suckhoeviet.2')">🚀 Đăng Ngay 1 Bài (@suckhoeviet.2)</button>
        <button class="btn btn-yellow" onclick="postNow('@suc.khoe.vang.268')">🚀 Đăng Ngay 1 Bài (@suc.khoe.vang.268)</button>
      </div>
    </div>

    <!-- CARD 3: BO LAP LICH 1 TIENG / 1 VIDEO & OFFLINE CACHE -->
    <div class="card">
      <h3>⏱️ 3. Lập Lịch Tự Động (1 Tiếng / 1 Video) & Kho Offline</h3>
      <div id="cache-detail" style="font-size:13px; color:var(--muted); margin-bottom:10px;">Đang kiểm tra kho Offline...</div>
      <div class="row">
        <button id="btn-toggle-sched" class="btn btn-green" onclick="toggleScheduler()">⏱️ Bật Tự Động Đăng (60 Phút / Video)</button>
        <button class="btn btn-blue" onclick="syncR630()">📥 Đồng Bộ Video Từ R630 Về Laptop</button>
      </div>
      <div class="row" style="margin-top:12px;">
        <label style="font-size:12px; color:var(--muted);">Chế độ thực thi trên Oppo A57:</label>
        <select id="post-mode-sel" onchange="saveMode()" style="flex:1;">
          <option value="PREPARE_AND_FILL">Chuẩn bị sẵn trên Oppo A57 (Tự chuyển TK + Nạp 1 Video + Mở màn hình gắn giỏ GMV Max)</option>
          <option value="FULL_AUTO_POST">Tự động 100% (Tự chuyển TK + Nạp 1 Video + Tự bấm nút Đăng)</option>
        </select>
      </div>
    </div>
  </div>

  <!-- BANG SO CAI CHONG DANG TRUNG 3 LOP -->
  <div class="card" style="margin-bottom:18px;">
    <h3>🛡️ Sổ Cái Chống Đăng Trùng 3 Lớp (SQLite SHA-256 File + Clip ID + Caption Hash)</h3>
    <div style="font-size:13px; color:var(--muted);">
      Mỗi video đã nạp/đăng trên Oppo A57 đều bị khóa cứng mã băm nhị phân <code>SHA-256</code> tại <code>C:\\TikTok_AutoHub\\data\\anti_duplicate_ledger.db</code>. Hệ thống chặn tuyệt đối việc đăng trùng video hoặc trùng clip nguồn trên cùng tài khoản.
    </div>
    <table>
      <thead>
        <tr>
          <th>Thời gian</th>
          <th>Tài khoản</th>
          <th>Clip Gốc</th>
          <th>Sản phẩm</th>
          <th>Mã Băm Video (SHA-256)</th>
          <th>Mã Băm Caption</th>
          <th>Trạng thái</th>
        </tr>
      </thead>
      <tbody id="ledger-tbody">
        <tr><td colspan="7" style="color:var(--muted);">Chưa có lịch sử đăng trong sổ cái.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- BANG KHO VIDEO DA PRE-CACHE TREN LAPTOP -->
  <div class="card">
    <h3>📦 Kho Video Đã Lưu Sẵn Trên Ổ C: Laptop (Dùng Khi Đi Ra Ngoài Không Có R630)</h3>
    <table>
      <thead>
        <tr>
          <th>Kênh Đích</th>
          <th>Giờ Lên Lịch</th>
          <th>Sản Phẩm & Shop GMV Max</th>
          <th>Caption Chuẩn SEO (3-4 dòng + 5 Hashtag)</th>
          <th>Trạng Thái Cache</th>
          <th>Thao Tác</th>
        </tr>
      </thead>
      <tbody id="queue-tbody"></tbody>
    </table>
  </div>
</div>

<script>
let currentSettings = {};

async function refreshStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    currentSettings = data.settings || {};
    const oppo = data.runtime.oppo_status || {};
    const r630 = data.runtime.r630_sync_status || {};

    document.getElementById('last-msg').textContent =
      `[${data.runtime.last_action_time}] ${data.runtime.last_action_result}`;

    const badges = [];
    if (oppo.connected) {
      badges.push(`<span class="badge b-ok">📱 Oppo A57: ĐÃ KẾT NỐI (${oppo.serial} • ${oppo.mode})</span>`);
    } else {
      badges.push(`<span class="badge b-warn">📱 Oppo A57: CHƯA KẾT NỐI</span>`);
    }
    badges.push(`<span class="badge b-info">📦 Kho Offline Laptop: ${r630.cached_offline_ready || 0} Video sẵn sàng</span>`);
    if (currentSettings.auto_scheduler_enabled) {
      const mins = Math.ceil((data.next_wait_seconds || 0) / 60);
      badges.push(`<span class="badge b-ok">⏱️ Auto 1 Tiếng/Video: ĐANG BẬT (Bài tiếp sau ~${mins} phút)</span>`);
    } else {
      badges.push(`<span class="badge b-warn">⏱️ Auto 1 Tiếng/Video: ĐANG TẮT</span>`);
    }
    document.getElementById('top-badges').innerHTML = badges.join('');

    document.getElementById('oppo-detail').innerHTML = oppo.connected
      ? `<span style="color:#4ade80;font-weight:700;">✓ Đã kết nối Oppo A57 (${oppo.serial})</span> — Sẵn sàng chuyển tài khoản & đẩy video.`
      : `<span>${oppo.detail || 'Chưa kết nối'}</span>`;

    document.getElementById('cache-detail').innerHTML =
      `Kho đệm trên Laptop (<code>C:\\TikTok_AutoHub\\video_cache</code>): <b>${r630.cached_offline_ready || 0}</b> video đã tải sẵn / <b>${r630.total_queue || 0}</b> bài trong hàng chờ.`;

    const btnSched = document.getElementById('btn-toggle-sched');
    if (currentSettings.auto_scheduler_enabled) {
      btnSched.textContent = '⏸️ Tắt Tự Động Đăng (Đang chạy 1 Tiếng / Video)';
      btnSched.className = 'btn btn-yellow';
    } else {
      btnSched.textContent = '⏱️ Bật Tự Động Đăng (60 Phút / Video)';
      btnSched.className = 'btn btn-green';
    }
    document.getElementById('post-mode-sel').value = currentSettings.post_mode || 'PREPARE_AND_FILL';

    // Render Ledger
    const lt = document.getElementById('ledger-tbody');
    if (data.ledger && data.ledger.length > 0) {
      lt.innerHTML = data.ledger.map(row => `
        <tr>
          <td>${row.posted_at}</td>
          <td><b>${row.channel}</b></td>
          <td><code>${row.clip_id}</code></td>
          <td>${row.product_name}</td>
          <td class="mono">${(row.file_sha256 || '').slice(0, 16)}...</td>
          <td class="mono">${(row.caption_sha256 || '').slice(0, 12)}...</td>
          <td><span class="badge b-ok">${row.post_mode}</span></td>
        </tr>
      `).join('');
    }

    // Render Queue
    const qt = document.getElementById('queue-tbody');
    if (data.ready_queue && data.ready_queue.length > 0) {
      qt.innerHTML = data.ready_queue.map(item => {
        const fname = (item.output_video || '').split('/').pop();
        return `
          <tr>
            <td><b style="color:var(--accent);">${item.channel}</b></td>
            <td>${item.scheduled_slot || 'Giãn cách 1h'}</td>
            <td><b>${item.product_name}</b><br><span class="mono">Shop ID: ${item.seller_id}</span></td>
            <td style="max-width:380px; white-space:pre-line; font-size:12px;">${item.caption_seo}</td>
            <td>${item.cached_offline ? '<span class="badge b-ok">✓ Đã lưu ổ C:</span>' : '<span class="badge b-warn">Chờ tải</span>'}</td>
            <td>
              <a class="btn btn-dark" href="/video?file=${encodeURIComponent(fname)}" target="_blank">👁️ Xem</a>
            </td>
          </tr>
        `;
      }).join('');
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

function connectOppo(ipPort) { apiPost('/api/connect_oppo', {ip_port: ipPort}); }
function pairOppo() {
  apiPost('/api/pair_oppo', {
    pair_ip_port: document.getElementById('pair-ip').value,
    pair_code: document.getElementById('pair-code').value
  });
}
function syncR630() { apiPost('/api/sync_r630', {}); }
function testSwitch(ch) { apiPost('/api/test_switch', {channel: ch}); }
function postNow(ch) { apiPost('/api/post_now', {channel: ch}); }
function toggleScheduler() {
  apiPost('/api/update_settings', {auto_scheduler_enabled: !currentSettings.auto_scheduler_enabled});
}
function saveMode() {
  apiPost('/api/update_settings', {post_mode: document.getElementById('post-mode-sel').value});
}

refreshStatus();
setInterval(refreshStatus, 8000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("=" * 72)
    print(" TIKTOK AUTOHUB - STANDALONE LAPTOP + OPPO A57 CONTROLLER")
    print(f" Giao dien Dieu khien: http://localhost:{PORT}")
    print(f" Thu muc Cache Offline: {CACHE_DIR}")
    print("=" * 72)
    t = threading.Thread(target=background_scheduler_loop, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), LaptopHubHandler)
    server.serve_forever()
