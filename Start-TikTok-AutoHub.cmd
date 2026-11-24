@echo off
chcp 65001 >nul
title TikTok AutoHub - Laptop & Oppo A57 Controller (http://localhost:8099)
echo ======================================================================
echo   KHOI DONG TIKTOK AUTOHUB (LAPTOP + OPPO A57 STANDALONE CONTROLLER)
echo   - Tu dong dong bo kho video Offline tu R630 ve C:\TikTok_AutoHub\video_cache
echo   - Tu dong ket noi Oppo A57 (USB / Wi-Fi / Hotspot khi di ra ngoai)
echo   - Chong dang trung 3 lop (SHA-256) & Dang gian cach 1 Tieng / 1 Video
echo ======================================================================
cd /d C:\TikTok_AutoHub
start "" "http://127.0.0.1:8099"
python -u C:\TikTok_AutoHub\laptop_control_hub.py
pause
