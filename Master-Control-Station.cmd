@echo off
chcp 65001 >nul
title TRAM KIEM SOAT TONG THE v3.0 - TIKTOK AUTOHUB (BAT / TAT BANG TAY)
:MENU
cls
echo ================================================================================
echo   🎛️ TRẠM KIỂM SOÁT MASTER v3.0 TIKTOK AUTOHUB (BẬT / TẮT BẰNG TAY KHÔNG CẦN AI)
echo ================================================================================
echo.
echo   --- [TRẠNG THÁI HIỆN TẠI TRÊN LAPTOP] ---
netstat -ano | findstr ":8099.*LISTENING" >nul && (echo   [🟢 ĐANG BẬT] 1. Trạm Master Laptop ^(http://127.0.0.1:8099^)) || (echo   [🔴 ĐANG TẮT] 1. Trạm Master Laptop ^(Port 8099^))
tasklist | findstr /I "cloudflared.exe" >nul && (echo   [🟢 ĐANG BẬT] 2. Host Từ Xa Master ^& Cứu Hộ iDRAC 192.168.1.11 ^(https://master.phamvuong.io.vn ^& https://idrac.phamvuong.io.vn^)) || (echo   [🔴 ĐANG TẮT] 2. Host Từ Xa Master ^& Cứu Hộ iDRAC 192.168.1.11 ^(cloudflared.exe^))
tasklist | findstr /I "adb.exe" >nul && (echo   [🟢 ĐANG BẬT] 3. Kết Nối Điện Thoại ADB ^(Oppo A57^)) || (echo   [🔴 ĐANG TẮT] 3. Kết Nối Điện Thoại ADB ^(Oppo A57^))
echo.
echo ================================================================================
echo   CHỌN THAO TÁC BẬT / TẮT BẰNG TAY:
echo   [1] ▶️ BẬT Trạm Master Laptop + Host Từ Xa (master.phamvuong.io.vn ^& idrac.phamvuong.io.vn)
echo   [2] ⏹️ TẮT HẲN Toàn Bộ Trạm Master Laptop + Host Từ Xa + ADB
echo   [3] ▶️ BẬT Riêng Đường Hầm Host Từ Xa ^& Cứu Hộ iDRAC 192.168.1.11 Trên Laptop
echo   [4] ⏹️ TẮT Riêng Đường Hầm Host Từ Xa Trên Laptop (cloudflared.exe)
echo   [5] 🔄 Khởi Động Lại Kết Nối ADB Oppo A57 (Chế độ WinUSB ổn định)
echo   [6] 🌐 Mở Giao Diện Master Từ Xa (https://master.phamvuong.io.vn)
echo   [7] 🛡️ Mở Trang Cứu Hộ Phần Cứng iDRAC R620 (https://idrac.phamvuong.io.vn)
echo   [8] ☁️ Mở Trực Tiếp Kho Video Server R630 (https://tiktok.phamvuong.io.vn)
echo   [0] Thoát Menu
echo ================================================================================
set /p choice="Nhập số (0-8) và nhấn Enter: "

if "%choice%"=="1" (
    echo Đang khởi động Trạm Master Laptop v3.0 và Đường hầm Từ Xa...
    set ADB_LIBUSB=0
    start "TikTok-AutoHub-8099" /min cmd /c "cd /d C:\TikTok_AutoHub && set ADB_LIBUSB=0 && python -u C:\TikTok_AutoHub\laptop_control_hub.py"
    timeout /t 3 >nul
    start "" "http://127.0.0.1:8099"
    goto MENU
)
if "%choice%"=="2" (
    call C:\TikTok_AutoHub\Stop-All-TikTok-AutoHub.cmd
    goto MENU
)
if "%choice%"=="3" (
    start "Cloudflared-Laptop-Master" /min "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --config "C:\TikTok_AutoHub\data\cloudflared\config.yml" run tiktok-laptop-master
    timeout /t 2 >nul
    goto MENU
)
if "%choice%"=="4" (
    taskkill /F /IM cloudflared.exe >nul 2>&1
    timeout /t 1 >nul
    goto MENU
)
if "%choice%"=="5" (
    set ADB_LIBUSB=0
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe kill-server
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe start-server
    C:\TikTok_AutoHub\tools\platform-tools\adb.exe devices -l
    pause
    goto MENU
)
if "%choice%"=="6" (
    start "" "https://master.phamvuong.io.vn"
    goto MENU
)
if "%choice%"=="7" (
    start "" "https://idrac.phamvuong.io.vn"
    goto MENU
)
if "%choice%"=="8" (
    start "" "https://tiktok.phamvuong.io.vn"
    goto MENU
)
if "%choice%"=="0" exit /b
goto MENU
