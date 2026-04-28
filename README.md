# Problem Map + AreaPulse Civic AI

Civic issue reporting platform for Delhi with AI assistant, Firebase backend, and Gemini-powered chat.

---

## ⚡ ONE-SHOT SETUP (Recommended)

You need 2 things:
1. Your Firebase service-account JSON → rename to `firebase_key.json` and drop in this folder
2. A free Gemini API key → https://aistudio.google.com/app/apikey

Then in PowerShell, in this folder, run:

```powershell
.\setup.ps1
```

That's it. The script creates the virtual environment, installs dependencies, asks for your Gemini key, creates `.env`, and starts the app.

After that, every time you want to start the app:

```powershell
.\run.ps1
```

---

### If PowerShell blocks the script

Run this once (PowerShell will ask before allowing):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Type `Y` to confirm, then re-run `.\setup.ps1`.

---

## Manual setup (if you don't want to use the script)

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env       # paste your Gemini key
python app.py
```

---

## ✅ Verify it's working

1. Open http://localhost:5000
2. Sign in with any name
3. Click the red AI button (bottom-right)
4. Ask: "why is delhi so polluted"
5. Terminal should show:
   ```
   [llm_chat] called | key_present=True | key_prefix=AIzaSy
   [llm_chat] Gemini SUCCESS, response length: 280
   ```

---

## Features

### Civic platform
- Report civic issues with auto-tagging (pothole, water, garbage, streetlight, traffic, noise, sewage, electricity, tree)
- Live heatmap of issues by area
- Upvote / verify / resolve workflow
- Community channels per area
- NGO + government agency directory with proximity search
- User reputation, points, leaderboard

### AreaPulse Civic AI (built-in)
- **Chat tab** — ask anything in natural language (Gemini-powered)
- **Insights tab** — auto-generated cards: hot zones, trends, top categories
- **Report Copilot** — paste a draft, get suggested category + severity + improved wording
- **Spam detection** — every report screened with confidence score
- **Live moderation** — banner under the description as you type
- **Map intelligence** — "show me potholes" plots filtered markers on the map

Smart routing: structured queries (maps, tables, area lookups) run **locally** with zero API cost. Only free-form chat ("why is...", "how do we...", "explain...") hits Gemini. Plus a 10-min response cache and a 12-req/min rate-limit guard so you stay well within the free tier.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `firebase_key.json` not found | Drop your Firebase service-account JSON in this folder, named exactly `firebase_key.json` |
| Quota / 429 error | Wait 60 seconds — Gemini free tier is 15/min |
| `key_present=False` in terminal | `.env` not loading. Verify it's named exactly `.env` (Windows hides extensions — show them!) and contains `GEMINI_API_KEY=AIzaSy...` |
| Port 5000 in use | Edit last line of `app.py`, change `port=5000` to `port=8000` |
| AI button missing | Hard-refresh browser: `Ctrl+Shift+R` |
| Anything else | Check the terminal — error messages there tell you exactly what's wrong |

---

## File structure

```
problem-map-FINAL/
├── setup.ps1              ← run this once
├── run.ps1                ← run this daily
├── app.py                 ← Flask backend
├── database.py            ← Firestore data layer
├── ai_engine.py           ← AI brain (Gemini + rule-based)
├── classifier.py          ← keyword tagger
├── requirements.txt
├── .env.example           ← template
├── .env                   ← your secrets (created by setup.ps1)
├── firebase_key.json      ← you add this
├── static/                ← CSS + JS
└── templates/             ← HTML pages (AI widget on every page)
```
