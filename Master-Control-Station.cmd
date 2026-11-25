@echo off
title TRAM KIEM SOAT MASTER v3.0 - TIKTOK AUTOHUB (BAT / TAT BANG TAY)
:MENU
cls
echo ================================================================================
echo   TRAM KIEM SOAT MASTER v3.0 TIKTOK AUTOHUB (BAT / TAT BANG TAY KHONG CAN AI)
echo ================================================================================
echo.
echo   --- [TRANG THAI HIEN TAI TREN LAPTOP] ---
netstat -ano | findstr ":8099.*LISTENING" >nul && (echo   [DANG BAT] 1. Tram Master Laptop ^(http://127.0.0.1:8099^)) || (echo   [DANG TAT] 1. Tram Master Laptop ^(Port 8099^))
tasklist | findstr /I "cloudflared.exe" >nul && (echo   [DANG BAT] 2. Host Tu Xa Master ^& Cuu Ho iDRAC 192.168.1.11 ^(https://master.phamvuong.io.vn ^& https://idrac.phamvuong.io.vn^)) || (echo   [DANG TAT] 2. Host Tu Xa Master ^& Cuu Ho iDRAC 192.168.1.11 ^(cloudflared.exe^))
tasklist | findstr /I "adb.exe" >nul && (echo   [DANG BAT] 3. Ket Noi Dien Thoai ADB ^(Oppo A57^)) || (echo   [DANG TAT] 3. Ket Noi Dien Thoai ADB ^(Oppo A57^))
echo.
echo ================================================================================
echo   CHON THAO TAC BAT / TAT BANG TAY:
echo   [1] BAT Tram Master Laptop + Host Tu Xa (master.phamvuong.io.vn ^& idrac.phamvuong.io.vn)
echo   [2] TAT HAN Toan Bo Tram Master Laptop + Host Tu Xa + ADB
echo   [3] BAT Rieng Duong Ham Host Tu Xa ^& Cuu Ho iDRAC 192.168.1.11 Tren Laptop
echo   [4] TAT Rieng Duong Ham Host Tu Xa Tren Laptop (cloudflared.exe)
echo   [5] Khoi Dong Lai Ket Noi ADB Oppo A57 (Che do WinUSB on dinh)
echo   [6] Mo Giao Dien Master Tu Xa (https://master.phamvuong.io.vn)
echo   [7] Mo Trang Cuu Ho Phan Cung iDRAC R620 (https://idrac.phamvuong.io.vn)
echo   [8] Mo Truc Tiep Kho Video Server R630 (https://tiktok.phamvuong.io.vn)
echo   [0] Thoat Menu
echo ================================================================================
set /p choice="Nhap so (0-8) va nhan Enter: "

if "%choice%"=="1" (
    echo Dang khoi dong Tram Master Laptop v3.0 va Duong ham Tu Xa...
    set ADB_LIBUSB=0
    start "TikTok-AutoHub-8099" /min cmd /c "cd /d C:\TikTok_AutoHub && set ADB_LIBUSB=0 && python -u C:\TikTok_AutoHub\laptop_control_hub.py"
    timeout /t 3 >nul
    start "" "http://127.0.0.1:8099"
    goto MENU
)
if "%choice%"=="2" (
    call C:\TikTok_AutoHub\Stop-All-TikTok-AutoHub.cmd
    timeout /t 2 >nul
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
