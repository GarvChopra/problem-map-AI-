# AreaPulse

**AI-Powered Civic Issue Heatmap for Delhi**

> Turning citizen complaints into actionable intelligence.

🔗 **Live:** https://areapulse-5ag9.onrender.com/

Delhi citizens file thousands of civic complaints every year — potholes, garbage, broken streetlights — but they're trapped across disconnected portals with no follow-up. AreaPulse unifies them into one AI-powered platform that auto-classifies issues, filters spam, builds a live heatmap, and routes high-priority cases to the right authority.

## Features

- **AI Vision Reporting** — Drop a photo, AI auto-fills the category, severity, and description (Groq Llama-Vision)
- **Live Heatmap** — Real-time map of civic issues across Delhi (Leaflet + Firestore)
- **Smart Chat Assistant** — Ask "compare Rohini vs Saket" or "show report Lajpat Nagar" and get a rich dashboard with bar charts, severity donut, 7-day trend, NGO list, and AI verdict
- **NGO + Government Routing** — 16 seeded NGOs and 12 government agencies; AI drafts formal complaint emails
- **Verification & Escalation** — 4-step status timeline (Open → Verified → Escalated → Resolved) with reputation points
- **Spam Detection** — 14-rule classifier filters fake reports
- **Community Feed** — Channel-based discussions per neighborhood

## Tech Stack

| Layer | Tech |
|---|---|
| **Backend** | Python 3.11 · Flask · Gunicorn |
| **Frontend** | Vanilla JS · Leaflet.js · CSS variables (light/dark mode) |
| **Database** | Firebase Firestore (9 collections, real-time sync) |
| **AI** | Groq Llama-4-Scout (Vision) · HF Llama-3.1 (Chat) · Custom NLP classifier |
| **Hosting** | Render.com |

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<your-username>/areapulse.git
cd areapulse

# 2. Setup
python -m venv venv
.\venv\Scripts\Activate.ps1     # Windows
# source venv/bin/activate      # macOS/Linux
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env and set: HF_TOKEN, GROQ_API_KEY, SECRET_KEY, ADMIN_PASSWORD

# 4. Add Firebase credentials
# Place your firebase_key.json in the project root

# 5. Run
python app.py
# Open http://localhost:5000
```

## Project Structure

```
areapulse/
├── app.py                 # Flask routes
├── ai_engine.py           # AI orchestration (vision, chat, spam, dashboard)
├── database.py            # Firestore layer
├── classifier.py          # Keyword tag classifier (9 categories)
├── requirements.txt
├── runtime.txt
├── static/
│   ├── style.css
│   ├── ai_assistant.css
│   └── ai_assistant.js
└── templates/
    ├── base.html          # Layout + AI widget
    ├── index.html         # Home + map + report form
    ├── issues.html        # Public issue grid
    ├── my_issues.html     # User's reports
    ├── community.html
    ├── ngos.html
    ├── reputation.html
    └── login.html
```

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `HF_TOKEN` | Yes | Hugging Face API token (chat LLM) |
| `GROQ_API_KEY` | Yes | Groq API key (Vision LLM) |
| `SECRET_KEY` | Yes | Flask session secret |
| `ADMIN_PASSWORD` | Yes | Gates the verify action |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional | Path to Firebase JSON in production |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Optional | Google OAuth |

## Team

**Team Nexons**
- Shashwat Shukla *(Team Lead)*
- Garv Chopra

Category: Smart Cities / Urban Governance

---

> *"Let's build a smarter, more responsive Delhi — one pin at a time."*
