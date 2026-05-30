# AGENTS.md

## Project Overview

Stock screening WeChat mini-app with Python/FastAPI backend.

- `backend/` - FastAPI server (port 8000), SQLite database, APScheduler for daily tasks
- `miniapp/` - WeChat mini-program frontend (no build step, edit files directly)

## Backend Development

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Server starts at http://localhost:8000. Database tables auto-create on startup.

## Key Architecture

- `main.py` - FastAPI app, all API routes
- `database.py` - SQLAlchemy models (User, Strategy, StrategyResult), `init_db()` creates tables
- `stock_service.py` - Stock data fetching (Tencent finance API), strategy execution, AI script generation
- `strategies/builtin.py` - 5 built-in strategy functions, exported as `STRATEGIES` dict
- `scheduler.py` - APScheduler, runs all active strategies daily at configured time

## Environment

Copy `backend/.env` and configure:
- `WECHAT_APPID` / `WECHAT_SECRET` - WeChat miniapp credentials
- `LLM_API_KEY` / `LLM_API_URL` / `LLM_MODEL` - DeepSeek/ChatGPT for AI strategy generation
- `DATABASE_URL` - defaults to `sqlite:///./stock_app.db`
- `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` - daily strategy execution time

## Important Patterns

- API responses use `{"code": 0, "data": ...}` format
- Custom strategies store AI-generated Python code in `script_code` column, executed via `exec()`
- Stock data comes from Tencent finance API (qq.com), not a paid data provider
- `stock_service.py` uses ThreadPoolExecutor for concurrent stock filtering
- Miniapp base URL is hardcoded in `miniapp/app.js`

## No Test/Lint/Typecheck

This project has no test suite, linter, or type checker configured. Verify changes by running the server and testing API endpoints manually.
