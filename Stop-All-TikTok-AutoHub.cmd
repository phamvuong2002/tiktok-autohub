@echo off
title TAT TOAN BO CHUONG TRINH TIKTOK AUTOHUB TREN LAPTOP
echo Dang dung Tram Dieu Khien Master Laptop (Port 8099), Cloudflare Tunnel va ADB Server...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
taskkill /F /IM cloudflared.exe >nul 2>&1
C:\TikTok_AutoHub\tools\platform-tools\adb.exe kill-server >nul 2>&1
echo [OK] Da tat hoan toan moi tien trinh chay ngam cua TikTok AutoHub tren Laptop!
