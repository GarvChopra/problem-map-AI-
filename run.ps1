# Daily-use launcher — just starts the app.
# (Run setup.ps1 first if you haven't yet.)

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Virtual environment not found. Run .\setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host ".env not found. Run .\setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting Problem Map at http://localhost:5000 ..." -ForegroundColor Green
& .\venv\Scripts\python.exe app.py
