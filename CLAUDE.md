# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智能选股助手 (Smart Stock Screener) — a WeChat Mini Program frontend + Python FastAPI backend that screens A-share stocks using built-in strategies and AI-generated custom strategies (via DeepSeek LLM).

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
python main.py              # Starts FastAPI on http://localhost:8000
```

No test framework is configured. No linter is configured.

### Mini Program

Open `miniapp/` directory in WeChat Developer Tools. Set `baseUrl` in `miniapp/app.js` to the backend address.

## Architecture

### Backend (FastAPI + SQLAlchemy)

- **main.py** — API entry point. Defines all endpoints, initializes DB and scheduler at startup via `lifespan`.
- **database.py** — SQLAlchemy models (User, Strategy, StrategyResult) and session management. Default DB is MySQL (`mysql+pymysql://`), configurable via `DATABASE_URL` env var.
- **stock_service.py** — Data layer. Fetches stock lists, K-line history, and realtime quotes from Tencent Finance API (`qt.gtimg.cn`). Includes an in-memory cache (1h TTL) for the full stock list. Also contains `generate_strategy_script()` for AI code generation.
- **scheduler.py** — APScheduler background cron job that runs all active strategies daily (default 08:30, configurable via `SCHEDULE_HOUR`/`SCHEDULE_MINUTE`).
- **strategies/** — Strategy modules. Each exports a `STRATEGIES` dict with `{key: {name, description, func, params}}`. Strategies are merged into a single dict in `main.py`.

### Strategy pattern

A strategy function has signature `(stock_info: dict, **params) -> bool`. It receives `{code, name, market, market_cap}` and calls `get_kline_data()`/`get_realtime_quote()` internally to decide if the stock passes.

AI custom strategies are stored as Python source in `Strategy.script_code` and executed via `exec()`. They must define a `check_stock(stock_info)` function.

### Mini Program (WeChat native framework)

- **app.js** — Global app. Calls `wx.login` on launch, posts to `/api/users` to get userId stored in `globalData`.
- **utils/request.js** — HTTP wrapper around `wx.request`. Auto-prepends `baseUrl`, sends `X-User-Id` header.
- **pages/index** — Home page: lists built-in strategies (tap to run) + custom strategy form (AI generation).
- **pages/strategy** — User's saved strategies management.
- **pages/result** — Historical execution results.
- **pages/stock** — Individual stock detail (quote + K-line).

### Data flow

1. User taps a built-in strategy on index page → `POST /api/strategies/builtin/{key}/run` → backend fetches stock list (quick 50 hot stocks or full ~5000), runs strategy function concurrently (ThreadPoolExecutor, 10 workers), returns matching stocks.
2. AI custom: user describes conditions → `POST /api/strategies/custom` → backend calls DeepSeek to generate Python script → saves to DB.
3. Scheduler runs all active strategies daily, saves results to `strategy_results` table.

## Environment Variables (backend/.env)

- `DATABASE_URL` — SQLAlchemy connection string
- `SCHEDULE_HOUR`, `SCHEDULE_MINUTE` — daily job time
- `LLM_API_KEY`, `LLM_API_URL`, `LLM_MODEL` — DeepSeek API config
- `WECHAT_APPID`, `WECHAT_SECRET` — WeChat credentials (optional)

## Key Conventions

- All API responses use `{"code": 0, "data": ...}` format on success.
- Strategy conditions are stored as JSON strings in the `conditions` column: `{"type": "strategy_key", "params": {...}}`.
- The project is written in Chinese with Chinese comments throughout. Keep new code and comments in Chinese to match.
- No test suite exists — test manually via API calls or WeChat Developer Tools.
