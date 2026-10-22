@echo off
setlocal
cd /d "%~dp0"
rem 取消开机自动启动（删除注册表「Run」里的本系统项）。「启动」文件夹里手工放的快捷方式需要自己删。
set "PY="
set "PYA="
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if defined PY goto :havepy
where py >nul 2>nul && set "PY=py" && set "PYA=-3"
if defined PY goto :havepy
where python >nul 2>nul && set "PY=python"
if defined PY goto :havepy
echo 没找到 Python。请用「便携版」压缩包（自带 python 文件夹），或先安装 Python 3.8 以上。
pause
exit /b 1
:havepy
"%PY%" %PYA% "%~dp0app\launcher.py" --remove-autostart
echo.
pause
