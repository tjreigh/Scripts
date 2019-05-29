::==============================================================================
:: This script is an automation to fix the random Wi-Fi dropouts on my computer
:: 
:: Author: TJDoesCode
:: 5/29/2019
::==============================================================================
@setlocal enableextensions enabledelayedexpansion
@echo off
:: Rezise console window
mode con: lines=36
mode con: cols=27

:loop
:: State detection loop - just pings google
set state=up
ping -n 1 www.google.com >nul: 2>nul:
if not !errorlevel!==0 set state=down
echo %TIME:~0,-1% ^| Link is !state!
if !state!==down goto :reset
ping -n 2 www.google.com >nul: 2>nul:
timeout /t 5 >nul
goto :loop
endlocal

:reset
:: Reset network adapter
echo Resetting Wi-Fi interface
netsh interface set interface "Wi-Fi" DISABLED
timeout /t 2 >nul
netsh interface set interface "Wi-Fi" ENABLED
timeout /t 15 >nul
:: Check if connection up
wmic path WIN32_NetworkAdapter where (NetConnectionID="Wi-Fi") get NetConnectionStatus | find /c "2" >NUL
if %ERRORLEVEL% EQU 0 ( 
    echo %TIME:~0,-1% ^| Link back up
    timeout /t 2 >nul
    goto :loop
) else ( 
    echo %TIME:~0,-1% ^| Link still not up
    timeout /t 2 >nul
    goto :reset
)
