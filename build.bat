@echo off
echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist sonic.spec del /q sonic.spec

echo Building Sonic executable...
"C:\Users\ukpno001\AppData\Local\Programs\Thonny\python.exe" -m PyInstaller --noconsole --icon=app_icon.ico --add-data "app_icon.ico;." --collect-all winrt sonic.py

echo.
echo Build complete! Check the dist\sonic folder.
pause