@echo off
chcp 65001 >nul
title TRAM KIEM SOAT TONG THE - TIKTOK AUTOHUB (BAT / TAT BANG TAY)
:MENU
cls
echo ================================================================================
echo   🎛️ TRẠM KIỂM SOÁT TỔNG THỂ TIKTOK AUTOHUB (BẬT / TẮT BẰNG TAY KHÔNG CẦN AI)
echo ================================================================================
echo.
echo   --- [TRẠNG THÁI HIỆN TẠI TRÊN LAPTOP] ---
netstat -ano | findstr ":8099.*LISTENING" >nul && (echo   [🟢 ĐANG BẬT] 1. Trạm Điều Khiển Laptop ^& Nhắc Lịch 1 Tiếng ^(http://127.0.0.1:8099^)) || (echo   [🔴 ĐANG TẮT] 1. Trạm Điều Khiển Laptop ^& Nhắc Lịch 1 Tiếng ^(Port 8099^))
netstat -ano | findstr ":8090.*LISTENING" >nul && (echo   [🟢 ĐANG BẬT] 2. Dịch Vụ Thu Livestream LiveVault ^(http://127.0.0.1:8090^)) || (echo   [🔴 ĐANG TẮT] 2. Dịch Vụ Thu Livestream LiveVault ^(Port 8090^))
tasklist | findstr /I "adb.exe" >nul && (echo   [🟢 ĐANG BẬT] 3. Dịch Vụ Kết Nối Điện Thoại ADB ^(Oppo A57^)) || (echo   [🔴 ĐANG TẮT] 3. Dịch Vụ Kết Nối Điện Thoại ADB ^(Oppo A57^))
echo.
echo ================================================================================
echo   CHỌN THAO TÁC BẬT / TẮT BẰNG TAY:
echo   [1] ▶️ BẬT Trạm Điều Khiển Laptop (http://127.0.0.1:8099) ^& Mở Giao Diện Web
echo   [2] ⏹️ TẮT HẲN Trạm Điều Khiển Laptop (Dừng chạy ngầm Port 8099)
echo   [3] ⏹️ TẮT Dịch Vụ Kết Nối ADB (Ngắt kết nối Oppo A57)
echo   [4] ▶️ BẬT Lại Dịch Vụ Kết Nối ADB (Oppo A57 - Chế độ WinUSB ổn định)
echo   [5] ▶️ BẬT Worker Tự Cắt Video 24/7 Trên Server Dell R630 (Qua Cloudflare/LAN)
echo   [6] ⏹️ TẮT Worker Tự Cắt Video 24/7 Trên Server Dell R630 (Tạm dừng cắt tự động)
echo   [7] 📊 Mở Dashboard Báo Cáo Đối Thủ Hàng Tuần (tiktok_competitor_dashboard.html)
echo   [8] 🌐 Mở Trực Tiếp Cổng Server R630 Từ Xa (https://tiktok.phamvuong.io.vn)
echo   [0] Thoát Menu
echo ================================================================================
set /p choice="Nhập số (0-8) và nhấn Enter: "

if "%choice%"=="1" (
    echo Đang khởi động Trạm Điều Khiển Laptop trên cổng 8099...
    set ADB_LIBUSB=0
    start "TikTok-AutoHub-8099" /min cmd /c "cd /d C:\TikTok_AutoHub && set ADB_LIBUSB=0 && python -u C:\TikTok_AutoHub\laptop_control_hub.py"
    timeout /t 2 >nul
    start "" "http://127.0.0.1:8099"
    goto MENU
)
if "%choice%"=="2" (
    echo Đang tắt Trạm Điều Khiển Laptop (Port 8099)...
    powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
    timeout /t 1 >nul
    goto MENU
)
if "%choice%"=="3" (
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe kill-server
    timeout /t 1 >nul
    goto MENU
)
if "%choice%"=="4" (
    set ADB_LIBUSB=0
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe kill-server
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe start-server
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe devices -l
    pause
    goto MENU
)
if "%choice%"=="5" (
    powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'https://tiktok.phamvuong.io.vn/api/r630_service?action=start&service=tiktok-worker' -Method Post -TimeoutSec 8 | ConvertTo-Json } catch { Invoke-RestMethod -Uri 'http://192.168.1.240:8088/api/r630_service?action=start&service=tiktok-worker' -Method Post -TimeoutSec 5 | ConvertTo-Json }"
    pause
    goto MENU
)
if "%choice%"=="6" (
    powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'https://tiktok.phamvuong.io.vn/api/r630_service?action=stop&service=tiktok-worker' -Method Post -TimeoutSec 8 | ConvertTo-Json } catch { Invoke-RestMethod -Uri 'http://192.168.1.240:8088/api/r630_service?action=stop&service=tiktok-worker' -Method Post -TimeoutSec 5 | ConvertTo-Json }"
    pause
    goto MENU
)
if "%choice%"=="7" (
    python C:\TikTok_AutoHub\weekly_competitor_report.py
    goto MENU
)
if "%choice%"=="8" (
    start "" "https://tiktok.phamvuong.io.vn"
    goto MENU
)
if "%choice%"=="0" exit /b
goto MENU
