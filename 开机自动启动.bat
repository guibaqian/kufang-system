@echo off
setlocal
cd /d "%~dp0"
rem 设置开机自动启动：写当前用户的注册表「Run」项（不需要管理员），开机后在后台启动，不弹浏览器，右下角托盘有图标。
rem 系统只会运行一个：「启动」文件夹里原来的快捷方式留着也不会重复启动。
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
"%PY%" %PYA% "%~dp0app\launcher.py" --install-autostart
echo.
pause
