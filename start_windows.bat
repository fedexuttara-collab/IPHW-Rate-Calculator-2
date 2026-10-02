@echo off
cd /d %~dp0
if not exist venv py -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
if "%ADMIN_PASSWORD%"=="" set ADMIN_PASSWORD=admin123
py app.py
