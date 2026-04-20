# AI Agent Studio — Setup & Deployment Guide

## 1. Install dependencies

```bash
pip install -r requirements.txt
sudo apt install ffmpeg   # or: brew install ffmpeg (macOS)
pip install yt-dlp        # for downloading YouTube videos
```

## 2. Google / YouTube API Setup

1. Go to https://console.cloud.google.com
2. Create a new project → Enable "YouTube Data API v3"
3. Go to Credentials → Create → OAuth 2.0 Client ID → Web Application
4. Add Authorized redirect URI: `http://localhost:5000/oauth2callback`
5. Download the JSON → save as `client_secrets.json` next to `server.py`

## 3. Run locally

```bash
python server.py
# Open http://localhost:5000 in your browser
```

---

## 4. Deploy FREE forever

### Option A — Render.com (BEST FREE OPTION)
- Free tier: 750 hrs/month (always-on with hobby plan $7/mo, or spin up on demand free)
- Steps:
  1. Push code to GitHub
  2. Go to https://render.com → New Web Service → Connect your repo
  3. Build command: `pip install -r requirements.txt`
  4. Start command: `gunicorn server:app`
  5. Add environment variable: `FLASK_SECRET=your-random-secret`
  6. Add `gunicorn` to requirements.txt
  7. Deploy — get a free `.onrender.com` URL

### Option B — Railway.app (EASIEST)
- $5 free credit/month, enough for light usage
  1. Install Railway CLI: `npm i -g @railway/cli`
  2. `railway login && railway init && railway up`
  3. Set env vars in dashboard
  4. Get a free `.up.railway.app` URL

### Option C — Vercel (frontend only)
- Vercel is for static/serverless, so use this only to host the HTML
- For the Python backend, use Render or Railway

### Option D — GitHub Pages (HTML only, no Python backend)
- Host just the frontend HTML for free forever at `username.github.io`
- The Python backend still needs to run on Render/Railway
  1. Put `templates/index.html` as `index.html` in a GitHub repo
  2. Settings → Pages → Deploy from main branch
  3. Update `const API = 'https://your-backend.onrender.com'` in the HTML

### Option E — Self-host on your PC (free forever, local only)
```bash
# Just run:
python server.py
# Access at http://localhost:5000
# Use ngrok to expose publicly for free:
ngrok http 5000
# Get a temporary public URL like https://abc123.ngrok.io
```

### Option F — Cloudflare Pages + Workers (truly free forever)
- Pages: host the HTML frontend free forever
- Workers: run a lightweight API (limited but free tier is generous)
  1. `npm install -g wrangler`
  2. Deploy HTML to Pages: `wrangler pages deploy .`
  3. For full Python support, combine with Render backend

---

## 5. Production checklist

- [ ] Change `FLASK_SECRET` to a long random string
- [ ] Add rate limiting: `pip install flask-limiter`
- [ ] Use HTTPS (automatic on Render/Railway/Vercel)
- [ ] Store YouTube credentials in a database, not in memory
- [ ] Add authentication to protect your agent endpoints
- [ ] Set `debug=False` in `server.py` for production

---

## 6. Environment variables

```
FLASK_SECRET=your-long-random-secret-key
GOOGLE_CLIENT_ID=from-google-cloud-console
GOOGLE_CLIENT_SECRET=from-google-cloud-console
PORT=5000
```

For Render: set these in the dashboard under Environment.
For Railway: `railway vars set FLASK_SECRET=...`