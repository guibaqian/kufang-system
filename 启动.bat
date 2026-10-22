@echo off
setlocal
cd /d "%~dp0"
rem 后台运行（没有黑窗口），右下角托盘有图标。已经在运行时再双击，只会打开浏览器。
if exist "%~dp0python\pythonw.exe" goto :portable
where pyw >nul 2>nul && goto :pyw
where pythonw >nul 2>nul && goto :pythonw
goto :console
:portable
start "" "%~dp0python\pythonw.exe" "%~dp0app\launcher.py" %*
exit /b 0
:pyw
start "" pyw -3 "%~dp0app\launcher.py" %*
exit /b 0
:pythonw
start "" pythonw "%~dp0app\launcher.py" %*
exit /b 0
:console
rem 没有 pythonw：只好用带窗口的 python（程序会自动关掉「快速编辑模式」，点窗口也不会卡住）
set "PY="
set "PYA="
if defined PY goto :havepy
where py >nul 2>nul && set "PY=py" && set "PYA=-3"
if defined PY goto :havepy
where python >nul 2>nul && set "PY=python"
if defined PY goto :havepy
echo 没找到 Python。请用「便携版」压缩包（自带 python 文件夹），或先安装 Python 3.8 以上。
pause
exit /b 1
:havepy
title Warehouse System - do not close this window
"%PY%" %PYA% "%~dp0app\launcher.py" --no-tray %*
echo.
echo 系统已停止。按任意键关闭窗口。
pause >nul
