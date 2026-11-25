@echo off
chcp 65001 >nul
title TAT TOAN BO CHUONG TRINH TIKTOK AUTOHUB TREN LAPTOP
echo Đang dừng Trạm Điều Khiển Master Laptop (Port 8099), Đường hầm Cloudflare Laptop và ADB Server...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
taskkill /F /IM cloudflared.exe >nul 2>&1
C:\TikTok_AutoHub\tools\platform-tools\adb.exe kill-server >nul 2>&1
echo ✓ Đã tắt hoàn toàn mọi tiến trình chạy ngầm của TikTok AutoHub trên Laptop!
timeout /t 2 >nul
