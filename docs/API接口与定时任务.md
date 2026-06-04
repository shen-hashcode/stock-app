# 智能选股助手 - 接口与定时任务文档

> 更新时间：2026-06-04
> 服务地址：`http://121.40.124.210:8000`（本地开发：`http://localhost:8000`）
> 响应格式约定：成功 `{"code": 0, "data": ...}`；失败 `{"code": <非零>, "message": "..."}`

## 业务错误码（response.code）

| code | 含义 | 典型来源 |
|---|---|---|
| 0 | 成功 | 全部接口 |
| 1 | 业务错误（参数错、资源不存在等） | 注册/登录/订阅 |
| 2 | 权限不足（未登录、试用过期、未订阅） | 内置策略执行、自定义策略创建 |
| 3 | 配额超限 | 创建自定义策略 |

> HTTP 状态码仅在 `raise HTTPException(...)` 时返回（如 404/500）；其它情况一律 200 + 业务 code。

---

## 接口总览

| 模块 | 接口 |
|---|---|
| 用户登录 | `POST /api/users`、`POST /api/wx_login`、`POST /api/register`、`POST /api/login` |
| 策略管理 | `GET /api/strategies/builtin`、`POST /api/strategies`、`POST /api/strategies/custom`、`GET /api/strategies/{user_id}` |
| 策略执行 | `POST /api/strategies/{strategy_id}/run`、`POST /api/strategies/builtin/{strategy_key}/run` |
| 结果查询 | `GET /api/results/{strategy_id}`、`GET /api/results/user/{user_id}`、`GET /api/strategies/running/{user_id}`、`GET /api/results/today/{user_id}` |
| 股票行情 | `GET /api/stock/{code}` |
| 订阅与支付 | `GET /api/subscription/packages`、`GET /api/subscription/status`、`POST /api/subscription/create_order`、`GET /api/subscription/order/{order_no}`、`POST /api/pay/callback` |

---

# 第一部分：用户登录

## 1. POST /api/users

创建或获取用户（小程序最早期的开放接口，**前端直接传 openid**，不走微信 code2session，仅用于早期联调；正式微信登录请用 `/api/wx_login`）。

**请求体**

```json
{
  "openid": "ou_xxxxxxx",
  "nickname": "可选",
  "phone": "可选"
}
```

**响应**

```json
{ "code": 0, "data": { "id": 12, "openid": "ou_xxxxxxx" } }
```

**逻辑**：按 openid upsert，存在直接返回 ID，不存在则新建。

---

## 2. POST /api/wx_login ★ 推荐微信小程序登录入口

接收 `wx.login` 拿到的 code，调微信 `jscode2session` 换 openid，按 openid upsert 用户。

**请求体**

```json
{ "code": "0xxxxxx", "nickname": "可选" }
```

**响应**

```json
{ "code": 0, "data": { "id": 12, "openid": "o_xxxxxx", "nickname": "" } }
```

**失败响应**

```json
{ "code": 1, "message": "服务端未配置微信 AppID / Secret" }
{ "code": 1, "message": "invalid code" }
```

**依赖环境变量**：`WECHAT_APPID`、`WECHAT_SECRET`（必须配置，否则报"未配置"）。

---

## 3. POST /api/register

手机号 + 密码注册。注册成功后 `users.openid` 写入 `phone_<手机号>`，**这种用户不能用微信支付**（订阅下单会被拦截）。

**请求体**

```json
{ "phone": "13800000000", "password": "至少6位", "nickname": "可选" }
```

**校验**：手机号 11 位 / 密码 ≥ 6 位 / 手机号未注册。
**响应**：`{ "code": 0, "data": { "id": 12, "phone": "...", "nickname": "..." } }`

---

## 4. POST /api/login

手机号 + 密码登录。

**请求体**：同 `/api/register`（不含 nickname）。
**响应**：`{ "code": 0, "data": { "id": 12, "phone": "...", "nickname": "..." } }`
**失败**：`{ "code": 1, "message": "手机号或密码错误" }`

---

# 第二部分：策略管理

## 5. GET /api/strategies/builtin

列出全部内置策略元信息（含参数 schema），供小程序展示选择。

**响应**

```json
{
  "code": 0,
  "data": [
    {
      "key": "rise_pullback",
      "name": "涨幅回调",
      "description": "前N日累计涨幅超过阈值，当日出现回调",
      "params": {
        "days": { "type": "int", "default": 3, "label": "上涨天数" },
        "rise_pct": { "type": "float", "default": 13, "label": "涨幅阈值(%)" },
        "market_cap_min": { "type": "float", "default": 50, "label": "最低市值(亿)" }
      }
    },
    ...
  ]
}
```

**当前内置策略一览**

| key | 名称 | 说明 |
|---|---|---|
| `rise_pullback` | 涨幅回调 | 前 N 日涨幅超阈值且当日回调 |
| `volume_breakout` | 放量突破 | 量能突然放大 + 价格上涨 |
| `ma_golden_cross` | 均线金叉 | 短期均线上穿长期均线 |
| `consecutive_rise` | 连续上涨 | 连续 N 天收阳 |
| `limit_up_open` | 涨停开板 | 昨涨停今开板低开 |
| `steady_rise` | 稳步上涨 | 短期累计涨幅在 [min, max] 区间 |

---

## 6. POST /api/strategies

创建/保存"用户实例化的内置策略"。

**查询参数**：`user_id`
**请求体**

```json
{
  "name": "我的涨幅回调",
  "description": "前3日累计涨13%回调买入",
  "conditions": "{\"type\": \"rise_pullback\", \"params\": {\"days\": 3}}"
}
```

> `conditions` 是 JSON 字符串，`type` 必须是内置策略 key。

**响应**：`{ "code": 0, "data": { "id": 7 } }`

---

## 7. POST /api/strategies/custom

提交 AI 自定义策略需求。**不会立即生成脚本**，仅入库 + 异步通知管理员处理。

**查询参数**：`user_id`
**请求体**：`{ "name": "...", "description": "用自然语言描述选股条件" }`

**前置校验**：
- 未订阅：`{ "code": 2, "message": "请先订阅套餐后再创建自定义策略" }`
- 自定义策略数 ≥ 套餐配额：`{ "code": 3, "message": "当前套餐最多创建X个..." }`

**成功响应**：`{ "code": 0, "data": { "id": 8 } }`

---

## 8. GET /api/strategies/{user_id}

获取用户全部策略列表（含内置实例 + 自定义）。

**响应**：`{ "code": 0, "data": [Strategy, ...] }`，按数据库返回顺序。

---

# 第三部分：策略执行

## 9. POST /api/strategies/{strategy_id}/run

执行**用户保存的策略**（异步 + Redis 缓存 + 分布式锁）。

**查询参数**：`force=true` 强制刷新缓存
**响应（缓存命中）**：

```json
{ "code": 0, "data": { "count": 12, "stocks": [...], "status": "completed", "from_cache": true } }
```

**响应（异步执行中）**：

```json
{ "code": 0, "data": { "status": "running", "message": "策略已开始执行，请稍后查询" } }
```

**缓存键**：`make_cache_key("saved", strategy_id)`
**锁键**：同名 + `:running` 后缀，TTL=300s（防止重复执行）

---

## 10. POST /api/strategies/builtin/{strategy_key}/run ★ 高频接口

直接运行内置策略（**三级缓存：Redis → 当天 DB → 异步执行**）。

**路径参数**：`strategy_key` 见接口 5 表格中的 key
**查询参数**：`force=true` 强制刷新；`params` 覆盖默认参数
**请求头**：`X-User-Id`（**必须**，用于试用/订阅校验）

**权限校验（守卫）**

| 用户状态 | 结果 |
|---|---|
| 未带 X-User-Id 或非法 | `{ "code": 2, "message": "请先登录" }` |
| 注册 ≤ 7 天 | ✅ 允许 |
| 注册 > 7 天且未订阅 | `{ "code": 2, "message": "试用期已结束，请订阅后继续使用" }` |
| 已订阅且未过期 | ✅ 不受限 |

**响应（缓存命中）**：同上，含 `from_cache` 或 `from_db` 字段
**响应（异步中）**：同上，`status: "running"`

**写库格式**（`strategy_results.stocks_json`）：

```json
{ "_strategy_key": "rise_pullback", "stocks": [...], "params": {...} }
```

（`strategy_id=0`、`user_id=0` 是公共结果约定）

---

# 第四部分：结果查询

## 11. GET /api/results/{strategy_id}

按策略 ID 查历史结果（按时间倒序）。

**查询参数**：`limit=10`（默认 10）
**响应**：`{ "code": 0, "data": [StrategyResult, ...] }`

## 12. GET /api/results/user/{user_id}

按用户 ID 查全部历史结果。

**查询参数**：`limit=20`
**响应**：同上

## 13. GET /api/strategies/running/{user_id}

查询该用户当前**正在执行**的策略（Redis SCAN `running:user:{user_id}:*`）。

**响应**：`{ "code": 0, "data": [{ "key": "rise_pullback", "name": "涨幅回调" }, ...] }`

## 14. GET /api/results/today/{user_id} ★ 首页常用

获取用户当天**全部**策略结果（含内置 + 自定义）。

**缓存**：Redis 键 `results:today:{user_id}:{YYYY-MM-DD}`，TTL 60 秒（仅用于同秒高频请求降压；每次都以 DB 为准）

**响应**

```json
{
  "code": 0,
  "data": [
    {
      "id": 101,
      "type": "builtin",
      "strategy_key": "rise_pullback",
      "strategy_name": "涨幅回调",
      "run_date": "2026-06-04",
      "stocks": [...],
      "count": 12,
      "created_at": "2026-06-04 16:05:23"
    },
    {
      "id": 102,
      "type": "custom",
      "strategy_id": 7,
      "strategy_name": "我的XX策略",
      "...": "..."
    }
  ],
  "from_cache": false
}
```

---

# 第五部分：股票行情

## 15. GET /api/stock/{code}

获取单只股票详情（实时行情 + 最近 10 天 K 线）。

**路径参数**：`code` 股票代码
**查询参数**：`market` 取值 `sh` / `sz`
**响应**

```json
{
  "code": 0,
  "data": {
    "quote": { "price": 10.96, "change_pct": 0.27, "volume": 766628, "market_cap": 2126.89 },
    "kline": [
      { "day": "2024-01-15", "open": 10.83, "close": 10.86, "high": 10.92, "low": 10.83, "volume": 793529 },
      ...
    ]
  }
}
```

---

# 第六部分：订阅与支付

## 16. GET /api/subscription/packages

列出所有上架套餐。

**响应**

```json
{
  "code": 0,
  "data": [
    { "id": 1, "name": "月度套餐", "description": "...", "price_cents": 1900, "duration_days": 30, "strategy_limit": 5 },
    ...
  ]
}
```

## 17. GET /api/subscription/status ★ 首页常用

查询当前用户订阅状态 + 试用期信息 + 自定义策略配额。

**查询参数**：`user_id`

**响应（未订阅，在试用期内）**

```json
{
  "code": 0,
  "data": {
    "has_subscription": false,
    "package_name": null,
    "strategy_limit": 0,
    "strategies_used": 0,
    "strategies_remaining": 0,
    "expired_at": null,
    "trial_active": true,
    "trial_days_remaining": 5,
    "trial_expired_at": "2026-06-09 14:23:11"
  }
}
```

**响应（已订阅）**

```json
{
  "code": 0,
  "data": {
    "has_subscription": true,
    "package_name": "月度套餐",
    "strategy_limit": 5,
    "strategies_used": 2,
    "strategies_remaining": 3,
    "expired_at": "2026-07-04 14:23:11",
    "trial_active": false,
    "trial_days_remaining": 0,
    "trial_expired_at": "2026-06-09 14:23:11"
  }
}
```

> `trial_*` 字段始终返回，便于前端统一展示。

## 18. POST /api/subscription/create_order

创建订阅订单 + 调用微信 JSAPI 统一下单，返回前端调起支付所需的 `payment_params`。

**查询参数**：`user_id`
**请求体**：`{ "package_id": 1 }`

**前置校验**：
- 套餐不存在/下架：`{ "code": 1, "message": "套餐不存在或已下架" }`
- 用户不存在：`{ "code": 1, "message": "用户不存在" }`
- openid 是 `phone_` 开头（手机号注册账号）：`{ "code": 1, "message": "微信支付需要微信授权登录" }`

**响应**

```json
{
  "code": 0,
  "data": {
    "order_no": "20260604xxxxxxxx",
    "payment_params": {
      "timeStamp": "...",
      "nonceStr": "...",
      "package": "prepay_id=wx...",
      "signType": "RSA",
      "paySign": "..."
    }
  }
}
```

**依赖**：`WECHAT_MCH_ID` / `WECHAT_API_KEY_V3` / `WECHAT_MCH_SERIAL_NO` / `WECHAT_MCH_PRIVATE_KEY_PATH` / `WECHAT_PAY_NOTIFY_URL` 全部配齐。

## 19. GET /api/subscription/order/{order_no}

查询订单当前状态（前端调起 `wx.requestPayment` 后轮询）。

**查询参数**：`user_id`
**响应**

```json
{
  "code": 0,
  "data": {
    "status": "pending|paid|expired|failed",
    "package_name": "月度套餐",
    "amount_cents": 1900,
    "created_at": "2026-06-04 14:23:11",
    "paid_at": "2026-06-04 14:23:50"
  }
}
```

## 20. POST /api/pay/callback ★ 微信支付服务端调用

**不要从前端调用**，仅供微信支付服务端回调。

- 验签（当前实现为占位，生产前需补全平台公钥验签）
- 解密 `resource` 字段（AES-256-GCM）
- `event_type == TRANSACTION.SUCCESS` → 找到订单 → 激活订阅（设置 `status=paid`、`expired_at = now + duration_days`）
- 异步通知管理员
- **幂等**：已 paid 的订单直接返回 SUCCESS
- 返回微信约定格式：`{"code": "SUCCESS", "message": ""}`

---

# 第七部分：定时任务

调度器：`apscheduler.BackgroundScheduler`，在 FastAPI `lifespan` 中启动。

| 任务 ID | 任务名 | Cron | 入口函数 | 默认时间 | 环境变量 |
|---|---|---|---|---|---|
| `daily_strategy` | 每日策略执行 | `H M * * *` | `daily_strategy_run` | 08:30 | `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` |
| `warmup_builtin` | 内置策略预热 | `H M * * *` | `warmup_builtin_strategies` | 16:00 | `BUILTIN_WARMUP_HOUR` / `BUILTIN_WARMUP_MINUTE` |
| `check_expired_subs` | 检查过期订阅 | `5 0 * * *` | `check_expired_subscriptions` | 00:05 | 无（硬编码） |

## 任务 1：daily_strategy_run（每日用户策略执行）

**默认时间**：每日 08:30
**作用**：跑全部 `strategies` 表里 `is_active=True` 的用户保存的策略

**逻辑**：
1. 查所有启用策略
2. `get_stock_list()` 获取全量股票（带 1 小时内存缓存）
3. 遍历每个策略
   - `type == "custom"`：`exec` 用户脚本拿 `check_stock` 函数
   - `type ∈ STRATEGIES`：取内置 func + 合并参数
4. 遍历股票执行 `check_func(stock)` → 命中的拉实时行情 → 收集
5. 写入 `strategy_results`（保留 `strategy_id` 和 `user_id`）

**异常隔离**：单个策略失败不影响其他策略，所有异常写日志。

## 任务 2：warmup_builtin_strategies（内置策略预热）★ 新增

**默认时间**：每日 16:00（A 股 15:00 收盘后）
**作用**：在用户访问高峰前，把全部 6 个内置策略预跑一遍，写库 + 回填 Redis，让用户当天查询直接命中缓存

**逻辑**：
1. 合并 `BUILTIN_STRATEGIES` + `STEADY_RISE_STRATEGIES` → 共 6 个
2. `get_stock_list()` 一次（之后 6 个策略共享内存缓存）
3. 串行跑每个策略（使用默认参数）：
   - 调 `_run_strategy_sync(check_func, stock_list)`
   - 写 `strategy_results`：`strategy_id=0`，`user_id=0`，`stocks_json={"_strategy_key": key, "stocks": [...], "params": {...}}`
   - 回填 Redis 键 `make_cache_key("builtin", key, params)`，TTL 到当日 24 点

**预计耗时**：单策略数分钟～十几分钟（5000 股 × 命中后拉实时行情），6 个串行 ~1 小时。

**异常隔离**：单个策略失败 continue 下一个，不中断整体流程。

## 任务 3：check_expired_subscriptions（订阅过期标记）

**时间**：每日 00:05
**作用**：把 `status=paid` 且 `expired_at <= now` 的订阅记录改为 `status=expired`

---

# 第八部分：缓存键约定（Redis）

| 键模式 | 用途 | TTL |
|---|---|---|
| `make_cache_key("builtin", strategy_key, params)` | 内置策略结果缓存 | 到当日 24 点 |
| `make_cache_key("saved", strategy_id)` | 用户保存策略结果缓存 | 到当日 24 点 |
| `<cache_key>:running` | 分布式锁（防重复执行） | 300s |
| `running:user:{user_id}:{strategy_key}` | 用户维度执行中标记（供 `/api/strategies/running` 查询） | 300s |
| `results:today:{user_id}:{YYYY-MM-DD}` | 用户当天聚合结果（每次都查 DB，仅做降压） | 60 秒 |

`get_ttl_seconds()` 返回**当前到当日 24 点的秒数**，全部当日缓存共用。

---

# 第九部分：依赖中间件

## 9.1 全局中间件

`CORSMiddleware`：允许所有来源（开发期配置，生产应收紧）。

## 9.2 自定义中间件

- `LoggingMiddleware`（如有）：请求日志记录

## 9.3 FastAPI 依赖

- `Depends(get_db)`：注入 SQLAlchemy Session（每请求新建一个）

---

# 第十部分：请求头约定

| Header | 来源 | 是否必传 | 用途 |
|---|---|---|---|
| `X-User-Id` | 小程序 `utils/request.js` 自动注入 | 内置策略执行**必传**；其他接口可选 | 试用/订阅校验 |
| `Content-Type: application/json` | 小程序 wx.request 默认 | POST 请求必传 | — |

---

# 第十一部分：环境变量速查

```env
# 数据库
DATABASE_URL=mysql+pymysql://root:root@localhost:3306/stock_app

# Redis
REDIS_URL=redis://localhost:6379/0

# 定时任务
SCHEDULE_HOUR=8
SCHEDULE_MINUTE=30
BUILTIN_WARMUP_HOUR=16
BUILTIN_WARMUP_MINUTE=0

# AI 自定义策略
LLM_API_KEY=
LLM_API_URL=
LLM_MODEL=

# 微信小程序登录
WECHAT_APPID=wx145f0e364826d176
WECHAT_SECRET=51cba2fc662ac5169de0f8d56d3ebd76

# 微信订阅消息通知
WX_NOTIFY_TEMPLATE_ID=

# 微信支付（拿到商户号后再填）
WECHAT_MCH_ID=
WECHAT_API_KEY_V3=
WECHAT_MCH_SERIAL_NO=
WECHAT_MCH_PRIVATE_KEY_PATH=
WECHAT_PAY_NOTIFY_URL=
```

---

# 附录：典型调用流程

## A. 微信小程序首次进入

```
wx.login -> code
  → POST /api/wx_login { code }
  → 拿到 userId 存进 storage
  → GET /api/subscription/status?user_id=X   // 显示试用剩余天数
  → GET /api/results/today/{userId}          // 首页展示当日已有结果
```

## B. 用户主动跑一个内置策略

```
POST /api/strategies/builtin/rise_pullback/run  Header: X-User-Id
  ↓
后端守卫（试用/订阅）
  ↓
Redis 命中？→ 直接返回
DB 当天结果命中？→ 返回 + 回填 Redis
都没有？→ background_tasks 异步执行，立即返回 { status: "running" }
  ↓
前端轮询 GET /api/results/today/{userId} 直到出现该策略结果
```

## C. 订阅下单到支付完成

```
GET /api/subscription/packages          // 用户选套餐
POST /api/subscription/create_order     // 后端创订单 + 微信统一下单
  → 返回 payment_params
wx.requestPayment(payment_params)       // 小程序调起支付
  ↓ 用户付款
微信支付服务端 → POST /api/pay/callback // 异步回调激活订阅
  ↓ 同时小程序轮询
GET /api/subscription/order/{order_no}?user_id=X  → status: paid
```