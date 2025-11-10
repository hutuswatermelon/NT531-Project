@echo off
echo [JSON-LOGGER] Bắt đầu ghi iperf3 JSON log...
setlocal enabledelayedexpansion

for /L %%i in (1,1,999) do (
    echo [SERVER] Chờ kết nối %%i...
    iperf3 -s -1 -J > "D:\NT531\server_json\session_%%i.json"
    echo [SERVER] Phiên %%i hoàn tất.
    timeout /t 2 >nul
)
pause
