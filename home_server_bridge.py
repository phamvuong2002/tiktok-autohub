# -*- coding: utf-8 -*-
"""
HOME SERVER REMOTE BRIDGE (PORT 4898 WAN & CLOUDFLARE ACCESS SSH TUNNEL ssh.phamvuong.io.vn)
Giup Laptop khi di ra ngoai (khac mang LAN voi Server R620/R630 o nha) ket noi ve nha qua 2 duong:
1. Duong 1 (Cloudflare Access SSH Tunnel co san tren may: ssh.phamvuong.io.vn -> 192.168.1.148):
   - Bam 1 nut tren giao dien de xac thuc trinh duyet (cloudflared access login https://ssh.phamvuong.io.vn)
   - Tu dong mo duong ham SSH Port-Forwarding:
     + 127.0.0.1:18088 -> 192.168.1.240:8088 (Container 240 Nha may cat video tren Server o nha)
     + 127.0.0.1:18006 -> 192.168.1.20:8006  (Giao dien Proxmox Server R620/R630 o nha)
     + Reverse Tunnel 18090 -> 127.0.0.1:8090 (De Server o nha lay duoc video tu LiveVault 8090 tren Laptop!)
   - Tu dong lay IP WAN Public hien tai cua mang Viettel o nha (da thoat CGNAT & mo port 4898).
2. Duong 2 (Ket noi truc tiep qua IP WAN Public / DDNS + Port 4898 da mo tren Router nha):
   - Cho phep nhap IP WAN / Ten mien DDNS:4898 (hoac tu dong cap nhat khi Tunnel ket noi).
"""
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from anti_dup_sync import DATA_DIR, SETTINGS_FILE, get_settings

BRIDGE_STATE = {
    "tunnel_active": False,
    "r630_remote_reachable": False,
    "home_wan_ip": "Chưa xác định (Bấm 'Đăng nhập & Mở Cầu Nối Server Nhà' để lấy IP WAN mới nhất)",
    "wan_port_4898_open": False,
    "proxmox_local_tunnel": "https://127.0.0.1:18006",
    "r630_worker_local_tunnel": "http://127.0.0.1:18088",
    "last_bridge_msg": "Đang ở khác mạng với Server nhà. Bạn có thể bật Cầu nối từ xa hoặc dùng bộ Cắt & Edit trực tiếp trên Laptop.",
    "tunnel_proc": None,
}


def check_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        s = socket.create_connection((host, port), timeout)
        s.close()
        return True
    except Exception:
        return False


def get_bridge_status() -> dict:
    # Kiem tra xem R630 co truy cap duoc truc tiep (192.168.1.240:8088) hoac qua SSH Tunnel (127.0.0.1:18088) khong
    direct_ok = check_port_open("192.168.1.240", 8088, 0.4)
    tunnel_ok = check_port_open("127.0.0.1", 18088, 0.4)
    BRIDGE_STATE["tunnel_active"] = tunnel_ok
    BRIDGE_STATE["r630_remote_reachable"] = direct_ok or tunnel_ok

    cfg = get_settings()
    if tunnel_ok and cfg.get("r630_url") != "http://127.0.0.1:18088":
        cfg["r630_url"] = "http://127.0.0.1:18088"
        SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    elif direct_ok and cfg.get("r630_url") != "http://192.168.1.240:8088":
        cfg["r630_url"] = "http://192.168.1.240:8088"
        SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    wan_ip = cfg.get("home_wan_ip", "")
    if wan_ip and re.match(r"^\d+\.\d+\.\d+\.\d+$", wan_ip):
        BRIDGE_STATE["home_wan_ip"] = f"{wan_ip}:4898"
        BRIDGE_STATE["wan_port_4898_open"] = check_port_open(wan_ip, 4898, 1.0)

    return {
        "tunnel_active": BRIDGE_STATE["tunnel_active"],
        "r630_direct_lan": direct_ok,
        "r630_remote_reachable": BRIDGE_STATE["r630_remote_reachable"],
        "home_wan_ip": BRIDGE_STATE["home_wan_ip"],
        "wan_port_4898_open": BRIDGE_STATE["wan_port_4898_open"],
        "proxmox_local_tunnel": BRIDGE_STATE["proxmox_local_tunnel"],
        "r630_worker_local_tunnel": BRIDGE_STATE["r630_worker_local_tunnel"],
        "last_bridge_msg": BRIDGE_STATE["last_bridge_msg"],
    }


def start_cloudflare_login_and_ssh_tunnel(custom_wan_ip: str = "") -> dict:
    """
    1. Neu nguoi dung nhap IP WAN moi cua mang nha (da mo port 4898 va thoat CGNAT), kiem tra ket noi port 4898.
    2. Kich hoat cloudflared access login https://ssh.phamvuong.io.vn (mo trinh duyet Laptop neu token het han)
       va mo duong ham SSH -L 18088:192.168.1.240:8088 -L 18006:192.168.1.20:8006 -R 18090:127.0.0.1:8090 seaweedfs-test!
    """
    custom_wan_ip = (custom_wan_ip or "").strip()
    if custom_wan_ip:
        ip_only = custom_wan_ip.split(":")[0]
        port_num = int(custom_wan_ip.split(":")[1]) if ":" in custom_wan_ip else 4898
        cfg = get_settings()
        cfg["home_wan_ip"] = ip_only
        SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        is_open = check_port_open(ip_only, port_num, 2.0)
        BRIDGE_STATE["home_wan_ip"] = f"{ip_only}:{port_num}"
        BRIDGE_STATE["wan_port_4898_open"] = is_open
        if is_open:
            BRIDGE_STATE["last_bridge_msg"] = (
                f"✓ Đã kết nối thông suốt tới Port {port_num} của mạng nhà ({ip_only}:{port_num} - Đã thoát CGNAT)!"
            )
        else:
            BRIDGE_STATE["last_bridge_msg"] = (
                f"⚠️ Không kết nối được tới {ip_only}:{port_num}. Có thể IP WAN động của nhà đã đổi — hãy bấm 'Mở Cầu Nối Qua ssh.phamvuong.io.vn' để tự lấy IP WAN mới và nối thẳng về R620/R630!"
            )
        return get_bridge_status()

    def _tunnel_worker():
        try:
            BRIDGE_STATE["last_bridge_msg"] = (
                "🌐 Đang mở trình duyệt xác thực Cloudflare Access (ssh.phamvuong.io.vn)... Hãy bấm 'Approve' trên tab trình duyệt vừa mở!"
            )
            # Xoa file lock cu neu bi treo
            cf_dir = Path(os.environ.get("USERPROFILE", r"C:\Users\girfl")) / ".cloudflared"
            if cf_dir.exists():
                for lf in cf_dir.glob("*.lock"):
                    try:
                        lf.unlink()
                    except Exception:
                        pass

            # Chay cloudflared access login (se mo trinh duyet tren Laptop de nguoi dung bam Approve)
            login_proc = subprocess.Popen(
                ["cloudflared", "access", "login", "https://ssh.phamvuong.io.vn"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            # Cho va doc URL login neu cloudflared in ra
            start_t = time.time()
            opened_url = False
            while time.time() - start_t < 45:
                if login_proc.poll() is not None:
                    break
                if cf_dir.exists() and not opened_url:
                    for uf in cf_dir.glob("*ssh.phamvuong.io.vn*.url"):
                        try:
                            u = uf.read_text(encoding="utf-8").strip()
                            if u.startswith("http"):
                                webbrowser.open(u)
                                opened_url = True
                        except Exception:
                            pass
                time.sleep(1.0)

            # Sau khi co token, lay IP WAN hien tai cua mang nha & mo duong ham SSH Port Forwarding
            ip_cmd = subprocess.run(
                [
                    "ssh",
                    "-o", "ConnectTimeout=10",
                    "-o", "StrictHostKeyChecking=no",
                    "seaweedfs-test",
                    "curl -s https://api.ipify.org",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            wan_ip = ip_cmd.stdout.strip()
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", wan_ip):
                cfg = get_settings()
                cfg["home_wan_ip"] = wan_ip
                SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                BRIDGE_STATE["home_wan_ip"] = f"{wan_ip}:4898"
                BRIDGE_STATE["wan_port_4898_open"] = check_port_open(wan_ip, 4898, 1.5)

            # Khoi dong duong ham SSH ngam noi Laptop -> R630 (192.168.1.240:8088) va Proxmox (192.168.1.20:8006)
            if not check_port_open("127.0.0.1", 18088, 0.5):
                p = subprocess.Popen(
                    [
                        "ssh",
                        "-N",
                        "-o", "ServerAliveInterval=20",
                        "-o", "ExitOnForwardFailure=yes",
                        "-L", "127.0.0.1:18088:192.168.1.240:8088",
                        "-L", "127.0.0.1:18006:192.168.1.20:8006",
                        "-R", "127.0.0.1:18090:127.0.0.1:8090",
                        "seaweedfs-test",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                BRIDGE_STATE["tunnel_proc"] = p
                time.sleep(3.0)

            if check_port_open("127.0.0.1", 18088, 1.0):
                cfg = get_settings()
                cfg["r630_url"] = "http://127.0.0.1:18088"
                SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                BRIDGE_STATE["tunnel_active"] = True
                BRIDGE_STATE["r630_remote_reachable"] = True
                BRIDGE_STATE["last_bridge_msg"] = (
                    f"✓ ĐÃ KẾT NỐI TỪ XA VỀ SERVER NHÀ THÀNH CÔNG! "
                    f"(IP WAN nhà: {BRIDGE_STATE['home_wan_ip']} • R630 Video Hub: http://127.0.0.1:18088 • Proxmox: https://127.0.0.1:18006)"
                )
            else:
                BRIDGE_STATE["last_bridge_msg"] = (
                    "⚠️ Chưa mở được đường hầm SSH. Hãy hoàn tất bấm 'Approve' trên cửa sổ trình duyệt Cloudflare Access rồi bấm lại nút Kết nối!"
                )
        except Exception as e:
            BRIDGE_STATE["last_bridge_msg"] = f"Lỗi mở cầu nối từ xa: {e}"

    threading.Thread(target=_tunnel_worker, daemon=True).start()
    return get_bridge_status()
