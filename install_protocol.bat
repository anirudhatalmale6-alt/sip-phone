@echo off
echo Installing sipphone:// URL protocol handler...
echo.

set "EXEPATH=%~dp0SIP-Phone.exe"
set "EXEPATH_REG=%EXEPATH:\=\\%"

echo Path: %EXEPATH%
echo.

reg add "HKEY_CLASSES_ROOT\sipphone" /ve /d "URL:SIP Phone Protocol" /f
reg add "HKEY_CLASSES_ROOT\sipphone" /v "URL Protocol" /d "" /f
reg add "HKEY_CLASSES_ROOT\sipphone\shell\open\command" /ve /d "\"%EXEPATH%\" \"%%1\"" /f

echo.
echo Done! sipphone:// links will now open SIP-Phone.
echo.
echo Test it by opening this in your browser:
echo   sipphone://0501234567
echo.
pause
