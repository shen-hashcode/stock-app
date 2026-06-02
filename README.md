# 智能选股助手

基于微信小程序 + FastAPI的智能选股系统，支持内置策略和AI自定义策略。

## 项目结构

```
stock_app/
├── backend/                      # FastAPI后端
│   ├── main.py                   # 主应用（API接口）
│   ├── database.py               # 数据库模型
│   ├── stock_service.py          # 股票数据服务
│   ├── scheduler.py              # 定时任务
│   ├── run_steady_rise.py        # 策略运行脚本
│   ├── .env                      # 环境配置
│   ├── requirements.txt          # Python依赖
│   └── strategies/               # 策略模块
│       ├── builtin.py            # 5个内置策略
│       └── steady_rise.py        # 稳步上涨策略
│
└── miniapp/                      # 微信小程序
    ├── app.js                    # 应用入口
    ├── app.json                  # 应用配置
    ├── app.wxss                  # 全局样式
    └── pages/
        ├── index/                # 首页（策略展示+AI创建）
        ├── strategy/             # 策略管理（执行+查看）
        └── result/               # 结果查看（历史记录）
```

## 快速开始

### 后端部署

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（编辑 .env 文件）
# DATABASE_URL=sqlite:///./test.db
# SCHEDULE_HOUR=16
# SCHEDULE_MINUTE=0

# 启动服务
python main.py
```

服务启动于 http://localhost:8000

### 小程序配置

1. 微信开发者工具导入 `miniapp` 目录
2. 修改 `app.js` 中的 `baseUrl` 为后端地址
3. 配置小程序 appid

## 功能特性

### 内置策略

| 策略 | 逻辑 | 默认参数 |
|------|------|----------|
| 涨幅回调 | 前N日累计涨幅超阈值，当日回调 | 3天/13%/50亿 |
| 放量突破 | 成交量放大且价格上涨 | 20天/2倍/50亿 |
| 均线金叉 | 短期均线上穿长期均线 | 5日/20日/50亿 |
| 连续上涨 | 连续N天收阳线 | 3天/50亿 |
| 涨停开板 | 昨日涨停，今日开板 | 50亿 |
| 稳步上涨 | 每日涨幅在0%~3%之间 | 6天/50亿 |

### AI自定义策略

用自然语言描述选股条件，AI自动生成Python脚本：

```
前3天累计涨幅超过15%，第4天回调，市值大于100亿
```

### 定时任务

- 每天16:00自动执行所有活跃策略
- 可通过 `.env` 配置执行时间

## API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/users` | POST | 创建/获取用户 |
| `/api/strategies/builtin` | GET | 获取内置策略列表 |
| `/api/strategies` | POST | 创建策略 |
| `/api/strategies/custom` | POST | AI生成策略 |
| `/api/strategies/{user_id}` | GET | 获取用户策略 |
| `/api/strategies/{id}/run` | POST | 执行策略 |
| `/api/strategies/builtin/{key}/run` | POST | 直接运行内置策略 |
| `/api/results/{id}` | GET | 获取执行结果 |
| `/api/stock/{code}` | GET | 获取股票详情 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | 微信小程序原生框架 |
| 后端 | FastAPI + SQLAlchemy |
| 数据库 | SQLite/MySQL |
| 定时任务 | APScheduler |
| 数据源 | 腾讯财经API |

## 数据库

```sql
-- 用户表
users (id, openid, nickname, phone, created_at, is_active)

-- 策略表
strategies (id, user_id, name, description, conditions, script_code, is_active, created_at, updated_at)

-- 结果表
strategy_results (id, strategy_id, run_date, stocks_json, created_at)
```

关系：User 1:N Strategy 1:N StrategyResult

## 环境配置

```env
# 数据库
DATABASE_URL=sqlite:///./test.db

# 定时任务
SCHEDULE_HOUR=16
SCHEDULE_MINUTE=0

# 微信小程序（可选）
WECHAT_APPID=your_appid
WECHAT_SECRET=your_secret

# AI接口（可选）
LLM_API_KEY=your_api_key
LLM_API_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

## 使用示例

### 运行策略脚本

```python
from stock_service import get_stock_list, run_strategy
from strategies.steady_rise import strategy_steady_rise

results = run_strategy(
    lambda stock: strategy_steady_rise(stock, days=5, min_pct=0, max_pct=3),
    max_workers=10
)
```

### 调用API

```bash
# 获取内置策略
curl http://localhost:8000/api/strategies/builtin

# 运行稳步上涨策略
curl -X POST http://localhost:8000/api/strategies/builtin/steady_rise/run?stock_limit=100 \
  -H "Content-Type: application/json" \
  -d '{"days": 5, "min_pct": 0, "max_pct": 3, "market_cap_min": 0}'
```
