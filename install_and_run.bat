@echo off
echo Installing SIP Phone...
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed!
    echo Please download and install Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install pyVoIP==1.6.8

:: Run the app
echo.
echo Starting SIP Phone...
python sip_phone.py

pause
