# Gmail Smart Cleaner

An intelligent email cleaning tool based on Google ADK + Gemini + Gmail API. Automatically generates Chinese summaries for unread emails, classifies them into three categories ("Action required" / "Read later" / "To delete"), and supports one‑click batch cleaning.

## Features

- 🔐 **Google OAuth 2.0** (only requests `gmail.readonly` and `gmail.modify` – never `gmail.send`)
- 📧 **Fetches unread emails from the last 7 days** (up to 50 messages, processed in‑memory only, no persistence)
- 🤖 **Gemini 2.5 Flash analysis**: ≤50‑word Chinese summary, category + short reason for each email
- 🗑️ **Batch operations**: mark as read / archive / move to trash (trash requires double‑confirmation)
- 🧩 **Frontend/Backend separation**: React + Vite frontend, FastAPI backend
- 🔧 **Agent‑ready architecture**: designed for Google ADK, easily extendable to multi‑agent collaboration

## Tech Stack

| Layer           | Technology                                                 |
| :-------------- | :--------------------------------------------------------- |
| Backend         | FastAPI + Uvicorn                                          |
| Agent Framework | Google ADK (design‑compatible)                             |
| AI Model        | Gemini 2.5 Flash (structured output)                       |
| Email API       | Google Gmail API v1                                        |
| OAuth           | google‑auth‑oauthlib                                       |
| Frontend        | React 18 + Vite 5 + TypeScript                             |
| Session         | Starlette SessionMiddleware (in‑memory / encrypted cookie) |

## Project Structure

Gmail-Smart-Cleaner/
├── backend/
│ ├── main.py # FastAPI entry (OAuth, routes, middleware)
│ ├── agent.py # Gemini Agent (summarisation + classification)
│ ├── gmail_service.py # Gmail API wrapper (read + batch actions)
│ ├── google_credentials.json # Google OAuth credentials (download manually)
│ └── .env # Environment variables (GEMINI_API_KEY, etc.)
├── frontend/
│ ├── src/
│ │ ├── App.tsx # Main UI (login status / email list / action buttons)
│ │ └── ...
│ ├── package.json
│ └── vite.config.ts # Vite proxy (/api → localhost:8000)
├── .agents/
│ └── skills/ # Agent Skills definitions (optional)
├── AGENTS.md # Project‑level agent behaviour rules
├── requirements.txt
└── README.md

## Installation & Configuration

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd Gmail-Smart-Cleaner
```

### 2. Backend environment

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend environment

```bash
cd ../frontend
npm install
```

### 4. Environment variables (`.env`)

Create a `.env` file inside `backend/`:

env

```
GEMINI_API_KEY=your_gemini_api_key_here
SESSION_SECRET_KEY=your_strong_random_secret_here
FRONTEND_URL=http://localhost:5173
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback
```



> ⚠️ Use a long random string for `SESSION_SECRET_KEY` (e.g., `openssl rand -hex 32`).

### 5. Google OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and enable Gmail API.
2. Create an OAuth 2.0 Client ID (application type: **Web application**).
3. Add `http://localhost:8000/api/auth/callback` as an authorised redirect URI.
4. Download the JSON credentials file, **rename** it to `google_credentials.json`, and place it in `backend/`.

### 6. (Optional) Proxy configuration

If your local network cannot directly reach Google services, configure a proxy in `main.py` inside the `get_oauth_flow` function:

```python
proxy_url = "http://127.0.0.1:your_proxy_port"
flow.oauth2session.proxies = {"http": proxy_url, "https": proxy_url}
```

## Running the Services

### Start the backend

```bash
cd backend
python -m backend.main
# or using uvicorn directly:
# uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Backend runs on `http://localhost:8000`.

### Start the frontend

```bash
cd frontend
npm run dev
```

Frontend runs on `http://localhost:5173`; Vite proxies `/api` requests to the backend on port 8000.

## Usage Flow

1. Open `http://localhost:5173`.
2. Click **“使用 Google 账号登录”** (Login with Google). You will be redirected to the Google OAuth consent screen.
3. After authorisation, you will be redirected back to the frontend, where unread emails are displayed.
4. Each email shows: sender, subject, summary, category (Action required / Read later / To delete).
5. Use the batch action buttons (e.g., “一键删除广告” – Delete All Ads) to clean up. **A confirmation dialog will appear before deleting.**

## Known Issues & Notes

- **Network**: Due to regional restrictions, you need a proxy for token exchange during local development. Use a tool like Clash and ensure the HTTP proxy port is correctly set.
- **Session storage**: Sessions are stored in memory (encrypted cookies); restarting the backend will require re‑login.
- **Email limit**: Only fetches the last 7 days of unread emails, up to 50 messages.
- **Delete operation**: Currently moves emails to **Trash** (recoverable), not permanently deleting them.

## Potential Extensions

- Integrate Google ADK for multi‑agent collaboration
- Allow user‑defined classification rules (keyword whitelists)
- Add historical analytics and a dashboard
- Support other email services (Outlook / QQ Mail)