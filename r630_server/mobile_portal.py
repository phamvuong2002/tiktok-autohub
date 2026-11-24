# -*- coding: utf-8 -*-
"""
R630 -> Oppo A57 Mobile Publishing Portal v3 (Full End-to-End Automated Control Center)
- Tu dong ket noi & canh cong LiveVault 24/7 (http://192.168.1.75:8090/d/...)
- Hien thi Kho Du Tru Dung Dan (Content Bank) + Loi thoai AI nghe duoc + Canh bao da cat Lazada
- Quan ly trang thai: Cho dang (READY) vs Da dang (POSTED) de dung dan 120 video/ca thu cho 3 kenh
- Ban thang video + nạp Caption sang Oppo A57 qua ADB Wi-Fi hoac tai 1 cham
"""
import cgi
import json
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tpcn_seo_engine import BASE_DIR, PRODUCT_CATALOG, QUEUE_FILE, generate_batch_for_product
from video_factory import INPUT_DIR, OUTPUT_DIR, render_pending_queue

PORT = 8088
DATA_DIR = BASE_DIR / "data"
ADB_CONFIG_FILE = DATA_DIR / "oppo_adb.json"
CONFIG_FILE = DATA_DIR / "worker_config.json"
PROCESSED_FILE = DATA_DIR / "processed_clips.json"


def load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(p: Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def get_adb_status() -> dict:
    target = load_json(ADB_CONFIG_FILE, {}).get("target", "")
    try:
        r = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=5)
        lines = [ln.strip() for ln in r.stdout.splitlines()[1:] if ln.strip()]
        return {"target": target, "devices": lines, "connected": any("device " in ln for ln in lines)}
    except Exception as e:
        return {"target": target, "devices": [str(e)], "connected": False}


PORTAL_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>R630 → Oppo A57 TikTok Automation Hub v3</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: "Segoe UI", Roboto, system-ui, -apple-system, sans-serif;
      background: #090e1a; color: #f1f5f9; font-size: 14px; line-height: 1.5;
      padding: 14px; max-width: 820px; margin: 0 auto;
    }
    .header {
      background: linear-gradient(135deg, #111c35, #0f172a);
      border: 1px solid #263554; border-radius: 14px; padding: 15px; margin-bottom: 14px;
    }
    h1 { font-size: 18px; font-weight: 800; color: #38bdf8; }
    h2 { font-size: 14.5px; font-weight: 700; color: #f8fafc; margin-bottom: 8px; }
    .sub { font-size: 12.5px; color: #94a3b8; margin-top: 4px; }
    .kpi-bar { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
    .kpi { background: #0b1222; border: 1px solid #1e293b; border-radius: 10px; padding: 9px 11px; text-align: center; }
    .kpi-num { font-size: 18px; font-weight: 800; color: #34d399; }
    .kpi-lbl { font-size: 11.5px; color: #94a3b8; }
    .alert-4g {
      margin-top: 10px; padding: 10px 12px; border-radius: 10px;
      background: rgba(251, 191, 36, 0.14); border: 1px solid rgba(251, 191, 36, 0.45);
      color: #fde68a; font-size: 12.5px; font-weight: 600;
    }
    .toolbar { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 14px; }
    .btn {
      padding: 8px 12px; border-radius: 9px; border: 1px solid #334155;
      background: #131d33; color: #e2e8f0; font-size: 13px; font-weight: 700;
      cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    }
    .btn.active { background: #2563eb; border-color: #60a5fa; color: #fff; }
    .btn-green { background: #059669; border-color: #34d399; color: #fff; width: 100%; padding: 11px; font-size: 13.5px; }
    .btn-blue { background: #4f46e5; border-color: #818cf8; color: #fff; width: 100%; padding: 11px; font-size: 13.5px; }
    .btn-cyan { background: #0284c7; border-color: #38bdf8; color: #fff; width: 100%; padding: 10px; font-size: 13px; margin-top: 7px; }
    .btn-done { background: #1e293b; border-color: #475569; color: #cbd5e1; width: 100%; padding: 9px; font-size: 12.5px; margin-top: 7px; }
    .card {
      background: #111827; border: 1px solid #1f2a40; border-radius: 14px;
      padding: 14px; margin-bottom: 14px; box-shadow: 0 6px 20px rgba(0,0,0,0.35);
    }
    .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 700; }
    .b-ch1 { background: rgba(251, 191, 36, 0.18); color: #fcd34d; border: 1px solid rgba(251, 191, 36, 0.45); }
    .b-ch2 { background: rgba(251, 113, 133, 0.18); color: #fda4af; border: 1px solid rgba(251, 113, 133, 0.45); }
    .b-ch3 { background: rgba(56, 189, 248, 0.18); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.45); }
    .b-gmv { background: rgba(16, 185, 129, 0.18); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.45); }
    .cover-box {
      margin: 10px 0; padding: 10px; border-radius: 9px;
      background: #facc15; color: #0f172a; font-weight: 800; text-align: center;
      white-space: pre-wrap; font-size: 13px; line-height: 1.4;
    }
    pre {
      background: #090e1a; border: 1px solid #26344e; border-radius: 9px;
      padding: 11px; white-space: pre-wrap; font-family: inherit; font-size: 13px; color: #e2e8f0; margin-bottom: 10px;
    }
    .shop-box {
      padding: 9px 11px; border-radius: 8px; background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(52, 211, 153, 0.35); font-size: 12.5px; color: #a7f3d0; margin-bottom: 10px;
    }
    .transcript-box {
      padding: 8px 10px; border-radius: 8px; background: #0b1222; border: 1px solid #1e293b;
      font-size: 12px; color: #94a3b8; margin-bottom: 10px;
    }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    select, input[type="text"], input[type="number"], input[type="file"] {
      background: #0b1222; color: #fff; border: 1px solid #334155; border-radius: 8px; padding: 8px 10px; font-size: 13px;
    }
    .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .status-line { font-size: 12.5px; color: #6ee7b7; margin-top: 6px; font-weight: 600; }
  </style>
</head>
<body>
  <div class="header">
    <h1>R630 (Xeon 24/7) → Oppo A57 TikTok Automation Hub v3</h1>
    <div class="sub">Tự động canh LiveVault (11h–13h) · AI nghe tiếng Việt tìm 3s Hook · Cắt bỏ Lazada · Đóng bìa vàng · Xếp kho dùng dần cho 3 kênh</div>
    <div class="kpi-bar">
      <div class="kpi"><div id="kpiClips" class="kpi-num">0</div><div class="kpi-lbl">Clip LiveVault đã hút</div></div>
      <div class="kpi"><div id="kpiReady" class="kpi-num" style="color:#38bdf8;">0</div><div class="kpi-lbl">Video Kho chờ đăng</div></div>
      <div class="kpi"><div id="kpiPosted" class="kpi-num" style="color:#fbbf24;">0</div><div class="kpi-lbl">Video Đã đăng</div></div>
    </div>
    <div class="alert-4g">
      ⚡ Quy tắc Oppo A57: Khi đổi Không gian 1 (@suckhoeviet.2) ↔ Không gian 2 (@suc.khoe.vang.268), hãy <strong>Bật Máy Bay 10 giây</strong> để đổi IP 4G mới!
    </div>
  </div>

  <!-- MODULE 1: LIVEVAULT AUTO-POLLER 24/7 -->
  <div class="card">
    <h2>1. Tự động canh cổng LiveVault 24/7 (Tự lấy video 1p → Nghe tiếng Việt → Cắt 3s Hook &amp; Bỏ Lazada)</h2>
    <div class="row">
      <input type="text" id="lvUrl" placeholder="Link LiveVault (http://192.168.1.75:8090/d/...)" style="flex:1;" />
      <button onclick="saveLvAndPoll()" id="pollBtn" class="btn active">⚡ Hút &amp; Cắt Video Mới Ngay</button>
    </div>
    <div id="lvStatus" class="status-line">Daemon R630 đang tự động canh cổng LiveVault mỗi 45 giây...</div>
  </div>

  <!-- MODULE 2: KET NOI OPPO A57 KHONG DAY QUA ADB WI-FI -->
  <div class="card">
    <h2>2. Kết nối Oppo A57 Không dây (ADB Wi-Fi — Bắn thẳng video + Caption sang Oppo A57)</h2>
    <div class="row">
      <input type="text" id="adbPairAddr" placeholder="Ghép nối IP:Port (lần đầu, vd 192.168.1.50:39123)" style="flex:1;" />
      <input type="text" id="adbPairCode" placeholder="Mã 6 số" style="width:95px;" />
      <button onclick="pairAdb()" class="btn">🔗 Ghép nối</button>
    </div>
    <div class="row" style="margin-top:8px;">
      <input type="text" id="adbConnAddr" placeholder="Kết nối IP:Port Gỡ lỗi không dây Oppo A57" style="flex:1;" />
      <button onclick="connectAdb()" class="btn active">📲 Kết nối Oppo A57</button>
    </div>
    <div id="adbActionMsg" class="status-line" style="color:#fcd34d;"></div>
    <div id="adbStatusBox" class="status-line" style="color:#93c5fd;"></div>
  </div>

  <!-- FILTER & CONTENT BANK -->
  <div class="toolbar">
    <button onclick="setFilter('all')" id="f-all" class="btn active">Kho chờ đăng (3 kênh)</button>
    <button onclick="setFilter('@suckhoeviet.2')" id="f-@suckhoeviet.2" class="btn">KG1: @suckhoeviet.2</button>
    <button onclick="setFilter('@suc.khoe.vang.268')" id="f-@suc.khoe.vang.268" class="btn">KG2: @suc.khoe.vang.268</button>
    <button onclick="setFilter('kenh_3')" id="f-kenh_3" class="btn">Kênh 3 (R630 Web)</button>
    <button onclick="setFilter('POSTED')" id="f-POSTED" class="btn">✓ Lịch sử Đã đăng</button>
  </div>

  <div id="feed"></div>

  <script>
    let ITEMS = [];
    let filterCh = 'all';

    async function loadAll() {
      const [qRes, wRes, aRes] = await Promise.all([
        fetch('/api/queue'),
        fetch('/api/worker_status'),
        fetch('/api/adb_status')
      ]);
      ITEMS = await qRes.json();
      const w = await wRes.json();
      const adb = await aRes.json();

      if (w.config?.livevault_url && !document.getElementById('lvUrl').value) {
        document.getElementById('lvUrl').value = w.config.livevault_url;
      }
      document.getElementById('kpiClips').textContent = w.processed_count || 0;
      document.getElementById('kpiReady').textContent = ITEMS.filter(x => x.status !== 'POSTED').length;
      document.getElementById('kpiPosted').textContent = ITEMS.filter(x => x.status === 'POSTED').length;

      if (adb.target && !document.getElementById('adbConnAddr').value) {
        document.getElementById('adbConnAddr').value = adb.target;
      }
      document.getElementById('adbStatusBox').textContent = adb.connected
        ? '✓ ĐÃ KẾT NỐI OPPO A57: ' + adb.devices.join(' | ')
        : 'Chưa nối ADB Wi-Fi (Bạn vẫn tải video 1 chạm cực nhanh bằng nút Tải Video màu xanh bên dưới)';
      document.getElementById('adbStatusBox').style.color = adb.connected ? '#6ee7b7' : '#94a3b8';

      render();
    }

    async function saveLvAndPoll() {
      const url = document.getElementById('lvUrl').value.trim();
      const btn = document.getElementById('pollBtn');
      btn.textContent = 'Đang hút & AI nghe lời thoại...';
      btn.disabled = true;
      document.getElementById('lvStatus').textContent = 'R630 đang hút video 1p mới từ LiveVault, nghe tiếng Việt tìm 3s Hook và cắt FFmpeg...';
      try {
        const r = await fetch('/api/poll_livevault?url=' + encodeURIComponent(url), { method: 'POST' });
        const res = await r.json();
        document.getElementById('lvStatus').textContent =
          `✓ Đã quét ${res.checked_clips} clip trên LiveVault → Xử lý mới ${res.new_clips_processed} clip → Sinh thêm ${res.rendered_videos} video vào Kho!`;
      } catch (e) {
        document.getElementById('lvStatus').textContent = 'Lỗi quét: ' + e;
      } finally {
        btn.textContent = '⚡ Hút & Cắt Video Mới Ngay';
        btn.disabled = false;
        await loadAll();
      }
    }

    async function markPosted(id) {
      await fetch('/api/mark_posted?id=' + encodeURIComponent(id), { method: 'POST' });
      await loadAll();
    }

    async function pairAdb() {
      const addr = document.getElementById('adbPairAddr').value.trim();
      const code = document.getElementById('adbPairCode').value.trim();
      if (!addr || !code) { alert('Nhập IP:Port ghép nối và mã 6 số trên Oppo A57'); return; }
      document.getElementById('adbActionMsg').textContent = 'Đang gửi lệnh adb pair tới ' + addr + '...';
      const r = await fetch(`/api/adb_pair?addr=${encodeURIComponent(addr)}&code=${encodeURIComponent(code)}`, { method: 'POST' });
      const res = await r.json();
      document.getElementById('adbActionMsg').textContent = 'Kết quả Ghép nối: ' + res.output;
      await loadAll();
    }

    async function connectAdb() {
      const addr = document.getElementById('adbConnAddr').value.trim();
      if (!addr) { alert('Nhập IP:Port Gỡ lỗi không dây trên Oppo A57'); return; }
      document.getElementById('adbActionMsg').textContent = 'Đang kết nối tới ' + addr + '...';
      const r = await fetch(`/api/adb_connect?addr=${encodeURIComponent(addr)}`, { method: 'POST' });
      const res = await r.json();
      document.getElementById('adbActionMsg').textContent = 'Kết quả Kết nối: ' + res.output;
      await loadAll();
    }

    async function pushToOppo(idx, btn) {
      const item = ITEMS[idx];
      btn.textContent = 'Đang bắn video sang Oppo A57...';
      const r = await fetch(`/api/adb_push?file=${encodeURIComponent(item.output_video)}`, { method: 'POST' });
      const res = await r.json();
      btn.textContent = res.ok ? '✓ Đã đẩy thẳng vào Thư viện ảnh Oppo A57!' : ('Lỗi: ' + res.output);
      setTimeout(() => { btn.textContent = '📲 3. Bắn thẳng sang Thư viện Oppo A57 (ADB)'; }, 3000);
    }

    function setFilter(ch) {
      filterCh = ch;
      document.querySelectorAll('.toolbar .btn').forEach(b => b.classList.remove('active'));
      const el = document.getElementById('f-' + ch);
      if (el) el.classList.add('active');
      render();
    }

    async function copyCap(idx, btn) {
      const item = ITEMS[idx];
      try {
        await navigator.clipboard.writeText(item.caption_seo);
        btn.textContent = '✓ ĐÃ COPY CAPTION + 5 TAG!';
        setTimeout(() => { btn.textContent = '📋 1. Copy Caption + 5 Tag'; }, 2200);
      } catch (e) {
        alert('Hãy chạm giữ khung Caption để copy');
      }
    }

    function render() {
      const list = ITEMS.map((x, idx) => ({ ...x, idx })).filter(x => {
        if (filterCh === 'POSTED') return x.status === 'POSTED';
        if (x.status === 'POSTED') return false;
        return filterCh === 'all' || x.channel === filterCh;
      });

      document.getElementById('feed').innerHTML = list.map(item => {
        const bClass = item.channel === '@suckhoeviet.2' ? 'b-ch1' : (item.channel === '@suc.khoe.vang.268' ? 'b-ch2' : 'b-ch3');
        const fixes = (item.policy_fixes || []).join(' · ');
        return `
          <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
              <span class="badge ${bClass}">${item.channel} · ${item.phone_space}</span>
              <span class="badge b-gmv">SEO 100/100 · ${item.clip_duration_sec}s · Zoom ${item.unique_profile.zoom}x</span>
            </div>
            <div style="font-weight:700; color:#f8fafc; font-size:15px;">${item.product_name}</div>
            <div style="font-size:12px; color:#94a3b8; margin-bottom:6px;">Nguồn cắt: <code>${item.source_video}</code> · Khung giờ dùng dần: <strong style="color:#38bdf8;">${item.scheduled_at}</strong></div>
            ${fixes ? `<div style="font-size:11.5px; color:#6ee7b7; margin-bottom:8px;">🛡️ Tự động xử lý: ${fixes}</div>` : ''}
            ${item.transcript ? `<div class="transcript-box">🎙️ <strong>AI Nghe lời thoại:</strong> ${item.transcript.slice(0, 260)}...</div>` : ''}

            <div class="shop-box">
              🛒 <strong>Gắn đúng Shop GMV Max:</strong> ${item.seller_name}<br/>
              Mã Shop (seller_id): <strong>${item.seller_id}</strong> · Bật <strong>Cấp quyền quảng cáo</strong>
            </div>

            <div style="font-size:12px; color:#94a3b8; font-weight:600;">Khung chữ bìa nền vàng chữ đen đã đóng lên video:</div>
            <div class="cover-box">${item.cover_text}</div>

            <div style="font-size:12px; color:#94a3b8; font-weight:600; margin-bottom:4px;">Caption + 5 Hashtag chuẩn SEO (0 từ cấm TPCN):</div>
            <pre>${item.caption_seo}</pre>

            <div class="grid-2">
              <button onclick="copyCap(${item.idx}, this)" class="btn btn-blue">📋 1. Copy Caption + 5 Tag</button>
              <a href="/download?file=${encodeURIComponent(item.output_video)}" class="btn btn-green">⬇ 2. Tải Video Unique</a>
            </div>
            <button onclick="pushToOppo(${item.idx}, this)" class="btn btn-cyan">📲 3. Bắn thẳng sang Thư viện Oppo A57 (ADB Wi-Fi)</button>
            ${item.status !== 'POSTED' ? `<button onclick="markPosted('${item.id}')" class="btn btn-done">✓ 4. Đánh dấu Đã Đăng (Chuyển vào Lịch sử để lấy bài kế tiếp)</button>` : ''}
          </div>`;
      }).join('') || `<div class="card" style="text-align:center; color:#94a3b8;">Chưa có video nào trong mục này. Bấm "⚡ Hút & Cắt Video Mới Ngay" ở trên!</div>`;
    }

    loadAll();
    setInterval(loadAll, 25000);
  </script>
</body>
</html>
"""


class PortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            data = PORTAL_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/api/queue":
            if not QUEUE_FILE.exists():
                generate_batch_for_product("bokhop_chondro")
            self._raw_json(QUEUE_FILE.read_bytes())
        elif parsed.path == "/api/worker_status":
            cfg = load_json(CONFIG_FILE, {})
            proc = load_json(PROCESSED_FILE, {})
            self._json_resp({"config": cfg, "processed_count": len(proc), "processed": proc})
        elif parsed.path == "/api/adb_status":
            self._json_resp(get_adb_status())
        elif parsed.path == "/download":
            qs = parse_qs(parsed.query)
            rel = qs.get("file", [""])[0]
            fpath = (BASE_DIR / rel).resolve()
            if fpath.exists() and str(fpath).startswith(str(BASE_DIR)):
                content = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", f'attachment; filename="{fpath.name}"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Video file not found")
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/poll_livevault":
            url = qs.get("url", [""])[0].strip()
            if url:
                cfg = load_json(CONFIG_FILE, {})
                cfg["livevault_url"] = url
                save_json(CONFIG_FILE, cfg)
            from livevault_auto_worker import poll_once
            res = poll_once()
            self._json_resp(res)

        elif parsed.path == "/api/mark_posted":
            item_id = qs.get("id", [""])[0]
            q = load_json(QUEUE_FILE, [])
            for x in q:
                if x.get("id") == item_id:
                    x["status"] = "POSTED"
            save_json(QUEUE_FILE, q)
            self._json_resp({"ok": True})

        elif parsed.path == "/api/adb_pair":
            addr = qs.get("addr", [""])[0]
            code = qs.get("code", [""])[0]
            r = subprocess.run(["adb", "pair", addr, code], capture_output=True, text=True, timeout=15)
            self._json_resp({"ok": r.returncode == 0, "output": (r.stdout + " " + r.stderr).strip()})

        elif parsed.path == "/api/adb_connect":
            addr = qs.get("addr", [""])[0]
            save_json(ADB_CONFIG_FILE, {"target": addr})
            subprocess.run(["adb", "disconnect"], capture_output=True, timeout=5)
            r = subprocess.run(["adb", "connect", addr], capture_output=True, text=True, timeout=15)
            self._json_resp({"ok": r.returncode == 0, "output": (r.stdout + " " + r.stderr).strip()})

        elif parsed.path == "/api/adb_push":
            rel = qs.get("file", [""])[0]
            fpath = (BASE_DIR / rel).resolve()
            remote = f"/sdcard/DCIM/Camera/{fpath.name}"
            devs = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5).stdout.splitlines()[1:]
            online = [ln.split()[0] for ln in devs if "\tdevice" in ln]
            s_args = ["-s", online[0]] if online else []
            r = subprocess.run(["adb"] + s_args + ["push", str(fpath), remote], capture_output=True, text=True, timeout=30)
            subprocess.run(
                ["adb"] + s_args + ["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{remote}"],
                capture_output=True,
                timeout=10,
            )
            self._json_resp({"ok": r.returncode == 0, "output": (r.stdout + " " + r.stderr).strip()})
        else:
            self.send_error(404)

    def _raw_json(self, raw: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _json_resp(self, obj: dict):
        self._raw_json(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), PortalHandler).serve_forever()
