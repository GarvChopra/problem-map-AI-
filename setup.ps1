# ════════════════════════════════════════════════════════════════════
#  Problem Map — One-shot Setup Script
# ════════════════════════════════════════════════════════════════════
#  Run this ONCE inside your problem-map-FINAL folder.
#  It will:
#    1. Create a Python virtual environment
#    2. Install all dependencies
#    3. Ask for your Hugging Face token
#    4. Check that firebase_key.json is in place
#    5. Create your .env file
#    6. Start the app
#
#  Usage in PowerShell (from inside the project folder):
#    .\setup.ps1
#
#  If PowerShell blocks the script, run this once first:
#    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# ════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Problem Map + AreaPulse Civic AI — Setup" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Verify we're in the right folder ─────────────────────
if (-not (Test-Path "app.py")) {
    Write-Host "ERROR: app.py not found in current folder." -ForegroundColor Red
    Write-Host "Please cd into the problem-map-FINAL folder before running this script." -ForegroundColor Yellow
    exit 1
}
Write-Host "[1/6] Project folder verified OK" -ForegroundColor Green

# ── Step 2: Check for firebase_key.json ──────────────────────────
if (-not (Test-Path "firebase_key.json")) {
    Write-Host ""
    Write-Host "[2/6] firebase_key.json NOT FOUND" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please drop your Firebase service-account JSON file into this folder." -ForegroundColor Yellow
    Write-Host "It must be named exactly: firebase_key.json" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "How to get it:" -ForegroundColor Cyan
    Write-Host "  1. Go to https://console.firebase.google.com" -ForegroundColor White
    Write-Host "  2. Open your project, Settings (gear), Service accounts" -ForegroundColor White
    Write-Host "  3. Click 'Generate new private key'" -ForegroundColor White
    Write-Host "  4. Rename the downloaded file to firebase_key.json" -ForegroundColor White
    Write-Host "  5. Drop it into this folder, then re-run setup.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}
Write-Host "[2/6] firebase_key.json found OK" -ForegroundColor Green

# ── Step 3: Create venv if it doesn't exist ──────────────────────
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "[3/6] Creating Python virtual environment..." -ForegroundColor Cyan
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create venv. Is Python installed?" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[3/6] Virtual environment already exists OK" -ForegroundColor Green
}

# ── Step 4: Install dependencies ─────────────────────────────────
Write-Host "[4/6] Installing dependencies (1-2 minutes)..." -ForegroundColor Cyan
& .\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. See message above." -ForegroundColor Red
    exit 1
}
Write-Host "[4/6] Dependencies installed OK" -ForegroundColor Green

# ── Step 5: Create .env if needed ────────────────────────────────
if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "[5/6] Setting up .env file" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Get your free Hugging Face token at:" -ForegroundColor White
    Write-Host "  https://huggingface.co/settings/tokens" -ForegroundColor Yellow
    Write-Host "  (Click 'New token' -> Type: 'Read' -> Create -> copy the hf_... key)" -ForegroundColor White
    Write-Host ""

    $hfToken = Read-Host "Paste your Hugging Face token (starts with hf_...)"

    if ([string]::IsNullOrWhiteSpace($hfToken)) {
        Write-Host "WARNING: No token entered. Creating .env with placeholder." -ForegroundColor Yellow
        Write-Host "         AI chat will use the local fallback only." -ForegroundColor Yellow
        $hfToken = "hf_PASTE_YOUR_TOKEN_HERE"
    }

    $envContent = @"
HF_TOKEN=$hfToken
SECRET_KEY=problemmap-$(Get-Random)
FLASK_DEBUG=true
FLASK_ENV=development
ADMIN_PASSWORD=admin123
"@
    Set-Content -Path ".env" -Value $envContent -Encoding UTF8
    Write-Host "[5/6] .env created OK" -ForegroundColor Green
} else {
    Write-Host "[5/6] .env already exists OK (delete it if you want to reconfigure)" -ForegroundColor Green
}

# ── Step 6: Run ──────────────────────────────────────────────────
Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Setup complete! Starting the app..." -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Open in browser:  http://localhost:5000" -ForegroundColor White
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor White
Write-Host ""

& .\venv\Scripts\python.exe app.py
