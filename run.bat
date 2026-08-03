@echo off
REM ── OK Smashed Burger — local dev launcher ────────────────────────────
cd /d "%~dp0"

set DATABASE_URL=sqlite:///dev.db
set SECRET_KEY=dev-secret
set JWT_SECRET_KEY=dev-jwt
set DEMO_PAYMENTS=true
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo [!] Virtualenv not found. Run:  python -m venv .venv  ^&^&  .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "instance\dev.db" (
  echo [*] First run - creating database and demo data...
  .venv\Scripts\python.exe -m flask --app wsgi db-create
  .venv\Scripts\python.exe -m flask --app wsgi seed
)

echo.
echo ==========================================================
echo   OK Smashed Burger running at http://127.0.0.1:8000
echo   Admin:    admin@oksmashedburger.com / admin123
echo   Customer: guest@oksmashedburger.com / guest123
echo   Press Ctrl+C to stop.
echo ==========================================================
echo.

.venv\Scripts\python.exe wsgi.py
