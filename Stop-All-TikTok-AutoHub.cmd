@echo off
chcp 65001 >nul
title TAT TOAN BO CHUONG TRINH TIKTOK AUTOHUB TREN LAPTOP
echo Đang dừng Trạm Điều Khiển Laptop (Port 8099) và ADB Server...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
C:\TikTok_AutoHub\tools\platform-tools\adb.exe kill-server
echo ✓ Đã tắt hoàn toàn các tiến trình chạy ngầm của TikTok AutoHub trên Laptop!
timeout /t 3
