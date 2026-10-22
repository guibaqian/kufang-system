@echo off
setlocal
rem 需要右键「以管理员身份运行」一次：放行 8080 端口，局域网手机才能打开
net session >nul 2>nul
if errorlevel 1 goto :noadmin
netsh advfirewall firewall delete rule name="WarehouseSystem 8080" >nul 2>nul
netsh advfirewall firewall add rule name="WarehouseSystem 8080" dir=in action=allow protocol=TCP localport=8080 profile=any
if errorlevel 1 goto :fail
echo 已放行 8080 端口，手机连同一个 WiFi 就能打开了。
goto :end
:noadmin
echo 需要管理员权限：请右键这个文件，选「以管理员身份运行」。
goto :end
:fail
echo 设置失败，请把上面的提示拍照发给维护人员。
:end
pause
