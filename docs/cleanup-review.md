# 代码清理建议清单

> 生成时间：2026-06-04
> 范围：`backend/*.py` + `miniapp/`
> 状态：**仅清单，未做任何修改**。请你逐项标注 ✅（同意删/改）/ ❌（保留）/ ❓（先聊聊），我据此动手。
>
> 注：以下条目按"风险等级"分类，A 类基本无副作用、C 类要慎重。

---

## A 类：低风险（未引用 / 孤儿样式 / 明显无用）

### 后端 - 未引用的 import / 类

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| A1 | main.py:23 | `from typing import ... List` | `List` 全文件未使用 | |
| A2 | main.py:37 | `from stock_service import ... run_strategy ...` | `run_strategy` 在 main 里没调用，实际走 `_run_strategy_sync` | |
| A3 | main.py:179-202 | `class StrategyResponse` | 全项目无引用，未挂任何接口 | |
| A4 | wechat_pay.py:16 | `import hashlib` | 全文件未使用 | |
| A5 | builtin.py:18 | `from stock_service import ... get_realtime_quote` | 文件内只用了 `get_kline_data` | |
| A6 | stock_service.py:488-492 | `extract_strategy_name()` | 全项目无调用 | |

### 后端 - 不一致的策略集合 import（潜在 bug）

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| A7 | scheduler.py:96 | `from strategies.builtin import STRATEGIES`（daily_strategy_run 中） | **没合并 steady_rise 的 STRATEGIES**，导致定时任务里 type=steady_rise 的策略直接被 skip。同一文件 warmup_builtin_strategies(190-195) 是合并的——**不一致** | |

### 后端 - sys.path hack 遗留

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| A8 | builtin.py:15-17 | `sys.path.append(...)` | 早期独立跑脚本的遗留，main 入口已包含 backend 目录 | |
| A9 | steady_rise.py:24-28 | 同上 | 同上 | |

### 小程序 - 孤儿样式（全局 grep 无消费方）

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| A10 | index.wxss:276-353 | `.modal/.modal-mask/.modal-content/.modal-title/.result-count/.result-number/.result-label/.result-list/.stock-info` | index.wxml 没有 modal 元素 | |
| A11 | result.wxss:32-56 | `.date-selector/.date-btn/.date-icon/.date-text` | result.wxml 没有日期选择器 | |
| A12 | result.wxss:169-174 | `.stock-market-cap` | wxml 中无此 class | |
| A13 | app.wxss:14-22 | `.card` | 全 6 个 wxml 都没用 `class="card"` | |
| A14 | app.wxss:24-32 | `.card-title` | 同上 | |
| A15 | app.wxss:144-149 | `.empty` | 各页面用的是 `.empty-state`，没用 `.empty` | |

### 小程序 - 未引用的工具方法

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| A16 | utils/request.js:42 | 导出 `put` | 全项目零调用 | |
| A17 | utils/request.js:43 | 导出 `del` | 全项目零调用 | |

---

## B 类：中风险（疑似废弃接口 / 模块 - 需要你确认产品意图）

### 后端 - 接口疑似未被前端调用

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| B1 | main.py:209-240 | `POST /api/users` + `UserCreate` 类 | 早期"直传 openid"的接口，已被 `/api/wx_login` 替代。**miniapp 中 grep 不到调用方** | |
| B2 | main.py:373-407 | `POST /api/strategies` + `StrategyCreate` 类 | 创建"用户实例化内置策略"。miniapp 中只调 `/api/strategies/custom`，**不调这个** | |
| B3 | main.py:834-868 | `GET /api/results/{strategy_id}` | miniapp 中 `/api/results/` 路径只匹配到 `/today/`，**没调这个** | |
| B4 | main.py:871-879 | `GET /api/results/user/{user_id}` | 同上 | |

> ⚠️ 这 4 个 endpoint 可能是给后台/管理员用的，或者你设计上"以后会用"。先问你：**是否确认 miniapp 之外完全不用？** 不用就删。

### 后端 - 残缺的 AI 链路

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| B5 | main.py:411-462 | `create_custom_strategy` 函数 | docstring 写"调用AI大模型生成脚本"，**实际只入库不调 AI**。和 stock_service 的 `generate_strategy_script` 形成断链 | 选择：补完 / 改 docstring 但保留人工处理 |
| B6 | stock_service.py:439-485 | `LLM_API_KEY` / `LLM_API_URL` / `LLM_MODEL` / `STRATEGY_PROMPT` / `generate_strategy_script()` | 整段 AI 代码无任何外部调用方 | 删除 / 补完接到 B5 |

> 这两条强相关：要么补完链路（B5 调用 B6 的函数），要么 B5 改文档说"人工处理"+ B6 整段删掉。

### 后端 - 死链路工具函数

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| B7 | stock_service.py:371-432 | `def run_strategy(...)` | main.py 唯一 import 它但**没调用**；docstring 提的 `run_steady_rise.py` 文件不存在 | |
| B8 | scheduler.py:323-332 | `def stop_scheduler()` | 全项目无调用方（lifespan 关闭也没调） | 删除 / 在 lifespan 接入 |

### 小程序 - 闲置的 globalData / 方法

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| B9 | app.js:4 | `globalData.userInfo` | 定义后全局零读写 | |
| B10 | app.js:6,7 等 | `globalData.userPhone` / `userNickname` | login.js 写入，但**没有任何页面读取**显示 | 删除 / 等个人中心页 |
| B11 | app.js:31 | `logout()` 方法 | 全局无调用方 | 删除 / 给个人中心做按钮 |

### 小程序 - strategy 页可疑功能

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| B12 | strategy.js:30-33 | `toggleStrategy()` 函数 | **空实现**——switch 开关切了什么也不发生 | 补完启停 API / 删除（开关变假交互） |
| B13 | strategy.js:35-53 + wxml | strategy 页的"立即执行"按钮 + 弹窗结果 | 与 result 页跳转查看路径重复，两套并存 | 二选一 |

---

## C 类：高风险（架构调整 / 重构 - 风险高，建议慎重）

### 跨文件重复实现（重构机会，但改起来要小心）

| # | 涉及位置 | 重复内容 | 风险 | 你的决定 |
|---|---|---|---|---|
| C1 | main.py:776-790 / scheduler.py:120-139 | "解析 conditions → 区分 custom/内置 → 构造 check_func" 几乎一字不差 | 抽公共会触及 2 个不同入口的关键路径 | |
| C2 | main.py:730-737 / scheduler.py:217-223 | 写 `StrategyResult(strategy_id=0, user_id=0, stocks_json=...)` | 同上 | |
| C3 | scheduler.py:71-175 daily_strategy_run | 与 main.py 的 `_execute_saved_strategy_background` 整体逻辑重叠 | 改动面很大 | |
| C4 | database/notify/redis_client/scheduler/stock_service 各自 `load_dotenv()` | 5+ 个文件都自己加载一遍 | 影响所有模块的 import 顺序 | |
| C5 | builtin.py + steady_rise.py | steady_rise 完全可以并入 builtin.py 的 STRATEGIES 字典 | 简单合并但要改 import | |

### 风格修复（不动逻辑、只动写法）

| # | 文件:行 | 内容 | 判断 | 你的决定 |
|---|---|---|---|---|
| C6 | scheduler.py:38,46 | `import logging` 重复创建 logger 不接 logger.py | scheduler 的日志会丢（logger.py 已 `propagate=False`） | **建议改**：换成 `from logger import logger` |
| C7 | stock_service.py:31,37 | 同上 | 同上 | **建议改** |
| C8 | scheduler.py:150 | `except: continue` 裸 except | 吃掉 KeyboardInterrupt | **建议改** `except Exception` |
| C9 | stock_service.py:306,363 | 裸 except / 异常静默 | 失败时无日志 | **建议改**：至少加 `logger.warning(...)` |
| C10 | main.py 多处 | 函数内 `from xxx import yyy` 局部 import（706, 766, 1199, 1261, 423, 1313 行） | 风格不一致 | 提到模块顶部（部分是为避免循环 import，要先验证再改） |
| C11 | database.py:58 | `engine = create_engine(..., echo=True)` | 与 logger.py 的 sql_logger 形成双重 SQL 日志输出 | 改为按 LOG_LEVEL 或独立 env 控制 |

### 小程序 - 重复样式抽公共

| # | 涉及位置 | 内容 | 你的决定 |
|---|---|---|---|
| C12 | 5 个 page wxss 都有 `page { background-color: #0d1117 }` 与 app.wxss 重复 | 删子文件副本 | |
| C13 | login.wxss vs app.wxss | `@keyframes shimmer` 一模一样 | 删 login 那份 | |
| C14 | app.wxss vs strategy.wxss | `.glow-divider` 重复 | 删 strategy 副本 | |
| C15 | index.wxss vs stock.wxss | `@keyframes pulse` 完全一致 | 上提 app.wxss | |
| C16 | index/strategy 各页 `.btn-create/.submit-btn` 与 app.wxss `.btn-primary` 同样的渐变 | 抽公共类 | |

---

## D 类：识别但**不建议改**（解释一下不改的原因）

| # | 内容 | 不改原因 |
|---|---|---|
| D1 | `wechat_pay.py:178` `verify_callback_signature` TODO | 你明确说过这是有意保留的占位 |
| D2 | `User.password_hash` / `phone` 字段 | 手机号注册路径在用，删字段需要 DB 迁移 |
| D3 | `User.is_admin` 字段 | notify.py 中用 |
| D4 | 全部数据库模型字段（即使没读） | 删字段需要 DB 迁移，风险高于收益 |
| D5 | builtin.py 里的策略函数（看似没被直接调用） | 通过 `STRATEGIES` 字典间接引用 |
| D6 | 全部 `@app.xxx` 装饰过的接口 | 不能通过 grep 调用方判断"无用" |

---

## 总计

- **A 类**：17 条（删了基本不会出问题）
- **B 类**：13 条（要你确认产品意图）
- **C 类**：16 条（架构调整，分量大，建议挑着做）
- **D 类**：6 条（已识别，不改）

---

## 怎么和我沟通你的决定

最简单的方式：直接回复"A 全删；B 中 B1/B2/B3/B4 都没用删了，B5 改文档保留人工处理 B6 删，B7/B8 删，B9/B10/B11 暂留；C 只做 C6/C7/C8/C9/C11/C12-C15"——大概这种粒度就够。

我会按你的清单一条条改，每改完一类汇报一次进度。