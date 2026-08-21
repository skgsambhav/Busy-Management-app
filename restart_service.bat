@echo off
:: Batch script to restart BusyApp Service
echo ===================================================
echo Restarting busyapp (busyapp.gopalmarketing.in)...
echo ===================================================
net stop busyapp
net start busyapp
echo.
echo ===================================================
echo Done! busyapp service restarted successfully.
echo ===================================================
timeout /t 3
