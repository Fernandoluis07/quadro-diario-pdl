@echo off
cd /d "%~dp0"
python -m backend.saude --notificar %*
