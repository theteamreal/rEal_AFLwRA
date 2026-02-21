@echo off
setlocal

:: Clear current server processes
echo [1/4] Stopping existing processes...
taskkill /F /IM daphne.exe 2>nul
taskkill /F /IM python.exe 2>nul

:: Discover network address
echo [2/4] Detecting Network ID...
python find_my_ip.py

:: Start Laptop Server (Daphne)
echo [3/4] Initializing Fedora Host via Daphne...
echo Server is launching on 0.0.0.0:8000
start /B daphne -b 0.0.0.0 -p 8000 fedguard.asgi:application

echo [4/4] Host Active.
echo ========================================
echo DO NOT CLOSE THIS WINDOW
echo ========================================
pause
