@echo off
cd /d "%~dp0"
echo Opening your private Role 3 review menu...
uv run --no-project --python 3.12 --with pydantic==2.12.3 python -m src.intelligence.review_menu
if errorlevel 1 pause
