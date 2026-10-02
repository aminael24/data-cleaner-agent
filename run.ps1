$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Le fichier .env a été créé. Ajoutez votre GROQ_API_KEY puis relancez run.ps1." -ForegroundColor Yellow
    exit 0
}

.\.venv\Scripts\python.exe -m streamlit run app.py
