@echo off
setlocal
rem 备用：托盘图标找不到时，用这个停止后台运行的库房系统（正常请用右下角图标 → 退出）
powershell -NoProfile -ExecutionPolicy Bypass -Command "$n=0; Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app\launcher.py*' -or $_.CommandLine -like '*app\server.py*' } | Where-Object { $_.CommandLine -notlike '*autostart*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $n++ }; exit $n"
set "N=%ERRORLEVEL%"
if "%N%"=="0" goto :none
echo 已停止库房系统（%N% 个进程）。
goto :end
:none
echo 库房系统没有在运行。
:end
pause
