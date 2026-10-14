@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r backend\requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
echo Painel: http://localhost:8000
echo Pare com Ctrl+C. Chaves ficam so no arquivo .env desta pasta.
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
