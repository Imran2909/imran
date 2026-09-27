# Imran Naukri Bot — Python AI Orchestrator (Naukri first)

Pan-India, past-24h only, in-site Apply only, headed keep-open browser, no apply cap.
Rule-first brain (3.1 yrs everywhere, positive defaults) + OpenRouter **free** fallback.

## Setup
```
cd naukri-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env   # fill NAUKRI_EMAIL, NAUKRI_PASSWORD, OPENROUTER_API_KEY
python -m src.orchestrator.run
```

Browser uses isolated `data/bot-profile` — stays open until you Ctrl+C.
Your own Chrome is untouched.

## Data
* `data/history.db` — dedupe
* `data/applied.csv` — job_title, company, job_url, applied_at, applicants, posted_ago, reason
* `data/skipped.csv` — same + reason
* `data/profile_refresh.log` — `updated at 1:10 PM...` every 30 min
* `data/bot.log` — full logs

## Safety
Stealth args + human delays + block detector (pauses 5 min on captcha).
No numeric cap per your spec, but 20-40s gap between applies to protect profile.

## Dashboard + CI/CD (GitHub only, no AWS)
* Local: `nk-dash` → http://127.0.0.1:8765 (Start/Stop buttons, filters, pagination)
* Public: push to `main` → Actions tests + builds, publishes `dashboard/` to
  GitHub Pages and the image to GHCR. One-time setup: repo Settings → Pages →
  Source: **GitHub Actions**.
* Refresh public numbers anytime: `nk-publish` (regenerates data.json, commits, pushes).

## Add LinkedIn later
Implement `src/sites/linkedin/` with same `Job` dataclass — orchestrator unchanged.
