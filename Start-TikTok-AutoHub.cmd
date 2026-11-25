@echo off
chcp 65001 >nul
title TikTok AutoHub Master v3.0 - Laptop & Remote Host (http://127.0.0.1:8099 & https://master.phamvuong.io.vn)
echo ============================================================================
echo   ⚡ KHOI DONG TRAM KIEM SOAT MASTER v3.0 (TIKTOK AUTOHUB & REMOTE HOST)
echo   - Giao dien tai Laptop      : http://127.0.0.1:8099
echo   - Dieu khien Master Tu Xa   : https://master.phamvuong.io.vn
echo   - Cuu ho iDRAC R620 (1.11)  : https://idrac.phamvuong.io.vn
echo   - Cuu ho iDRAC Du Phong     : https://idrac-rescue.phamvuong.io.vn
echo   - Cuu ho Proxmox (1.20)     : https://pve-rescue.phamvuong.io.vn
echo ============================================================================
cd /d C:\TikTok_AutoHub
set ADB_LIBUSB=0
start "" "http://127.0.0.1:8099"
python -u C:\TikTok_AutoHub\laptop_control_hub.py
pause
