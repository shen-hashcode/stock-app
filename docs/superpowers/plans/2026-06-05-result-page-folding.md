# 结果页折叠功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在结果页（miniapp/pages/result/）为每张策略卡片增加股票列表折叠功能，默认全部收起，点击卡片头部切换。

**Architecture:** 纯小程序前端改动，无后端 API 改动。给从后端拉到的每条 result 注入本地 UI 字段 `collapsed: true`；wxml 用 `wx:if="{{!item.collapsed}}"` 控制股票列表显隐；点击 `result-header` 触发 `toggleCard`，用动态键名 setData 局部更新。

**Tech Stack:** WeChat Mini Program（原生框架，WXML/WXSS/JS）。

**Spec:** `docs/superpowers/specs/2026-06-05-result-page-folding-design.md`

**Note:** 项目无测试框架（CLAUDE.md 明示）。本项功能涉及小程序 UI，自动化测试不可行，因此采用"代码改动 + 手动在微信开发者工具验证"的节奏，而非 TDD。每个 Task 结束后用列出的"手动验证步骤"在开发者工具里跑一遍再 commit。

---

## File Structure

仅修改以下 3 个文件，无新建：

- `miniapp/pages/result/result.js` — 新增 `toggleCard` 方法；在 `loadTodayResults` 注入 `collapsed: true`。
- `miniapp/pages/result/result.wxml` — `result-header` 加 `bindtap`/`data-index`；右侧加折叠箭头；`stock-list` 加 `wx:if`。
- `miniapp/pages/result/result.wxss` — 新增 `.fold-arrow`、`.fold-arrow.expanded`、`.result-header:active` 样式。

---

## Task 1：默认收起 — 数据注入

**Files:**
- Modify: `miniapp/pages/result/result.js:17-31`

- [ ] **Step 1：修改 `loadTodayResults`，给每条结果注入 `collapsed: true`**

把现有的 `result.js` 中 `loadTodayResults` 方法替换为以下内容（仅 `then(res => {...})` 内的成功分支改动，其余保留）：

```js
loadTodayResults() {
  const userId = app.globalData.userId
  if (!userId) return

  this.setData({ loading: true })
  get(`/api/results/${userId}`).then(res => {
    if (res.code === 0) {
      const results = (res.data || []).map(r => ({ ...r, collapsed: true }))
      this.setData({ results, loading: false })
    } else {
      this.setData({ loading: false })
    }
  }).catch(() => {
    this.setData({ loading: false })
  })
},
```

关键点：
- 用对象展开 `{ ...r, collapsed: true }`，不覆盖后端字段。
- 仅在成功分支（`res.code === 0`）做注入，保持失败/异常分支不变。

- [ ] **Step 2：手动验证（开发者工具）**

  1. 微信开发者工具打开 `miniapp/`，编译运行。
  2. 进入"结果"页面。
  3. 期望：所有策略卡片只显示头部（策略名 + xx 只），不显示股票列表。
  4. 控制台 AppData 面板里检查 `results[0].collapsed === true`。

- [ ] **Step 3：commit**

```bash
git add miniapp/pages/result/result.js
git commit -m "feat(result): 注入 collapsed 字段，默认全部收起"
```

---

## Task 2：折叠 UI — wxml 结构

**Files:**
- Modify: `miniapp/pages/result/result.wxml:22-45`

- [ ] **Step 1：修改 result-card 内部结构**

把现有 `result.wxml` 中 `result-card` 整块（第 22-45 行）替换为：

```xml
<view class="result-card" wx:for="{{results}}" wx:key="id">
  <view class="result-header" bindtap="toggleCard" data-index="{{index}}">
    <view class="result-date">
      <text class="date-dot"></text>
      {{item.strategy_name}}
    </view>
    <view class="result-count">
      <text class="count-number">{{item.count}}</text> 只
      <text class="fold-arrow {{item.collapsed ? '' : 'expanded'}}">∨</text>
    </view>
  </view>
  <view class="stock-list" wx:if="{{!item.collapsed}}">
    <view class="stock-item" wx:for="{{item.stocks}}" wx:for-item="stock" wx:key="code" bindtap="goStockDetail" data-code="{{stock.code}}" data-market="{{stock.market}}">
      <view class="stock-info">
        <view class="stock-name">{{stock.name}}</view>
        <view class="stock-code">{{stock.code}}</view>
      </view>
      <view class="stock-data">
        <view class="stock-change {{stock.quote.change_pct > 0 ? 'up' : 'down'}}">
          {{stock.quote.change_pct || '--'}}%
        </view>
      </view>
    </view>
  </view>
</view>
```

变化点：
- 第 23-31 行 `result-header` 加 `bindtap="toggleCard" data-index="{{index}}"`。
- `result-count` 内追加 `<text class="fold-arrow {{item.collapsed ? '' : 'expanded'}}">∨</text>`。
- `stock-list` 外层加 `wx:if="{{!item.collapsed}}"`。
- 内部 `stock-item` 循环和点击逻辑保持不变。

- [ ] **Step 2：手动验证（开发者工具）**

  1. 重新编译。
  2. 期望：每张策略卡片头部右侧能看到一个 `∨` 箭头，下方股票列表仍是隐藏的。
  3. 此时点击卡片头部尚不会展开（toggleCard 还没实现，控制台会报错"toggleCard is not a function"——这是预期，Task 3 修复）。

- [ ] **Step 3：commit**

```bash
git add miniapp/pages/result/result.wxml
git commit -m "feat(result): 卡片头部加折叠箭头与点击事件，股票列表受 collapsed 控制"
```

---

## Task 3：折叠切换 — toggleCard 方法

**Files:**
- Modify: `miniapp/pages/result/result.js`（在 `goStockDetail` 之前插入新方法）

- [ ] **Step 1：在 Page 对象中新增 `toggleCard` 方法**

在 `result.js` 现有 `goStockDetail` 方法之前插入：

```js
toggleCard(e) {
  const i = e.currentTarget.dataset.index
  const key = `results[${i}].collapsed`
  this.setData({ [key]: !this.data.results[i].collapsed })
},
```

要点：
- 用动态键名 `results[${i}].collapsed` 局部 setData，避免整张列表重渲。
- `data-index="{{index}}"` 在 wxml 已经传过来，这里直接读 `dataset.index`。

完成后 `result.js` 中 Page 对象方法顺序应为：`onShow → loadTodayResults → checkRunning → toggleCard → goStockDetail`。

- [ ] **Step 2：手动验证（开发者工具）**

  1. 重新编译。
  2. 进入"结果"页面，依次：
     - 点击第一张卡片头部 → 股票列表展开，箭头变为指向上方（旋转 180°）。
     - 再次点击 → 列表收起，箭头复位。
     - 点击第二张卡片头部 → 第二张展开，不影响第一张状态。
     - 点击已展开卡片内的某只股票 → 跳转到股票详情页（验证 `goStockDetail` 未被破坏）。
  3. AppData 面板里观察对应 `results[i].collapsed` 翻转。

- [ ] **Step 3：commit**

```bash
git add miniapp/pages/result/result.js
git commit -m "feat(result): 新增 toggleCard 方法切换卡片折叠状态"
```

---

## Task 4：折叠样式 — 箭头与点击反馈

**Files:**
- Modify: `miniapp/pages/result/result.wxss`（在文件末尾追加）

- [ ] **Step 1：追加折叠相关样式**

在 `result.wxss` 文件末尾追加：

```css
/* 折叠箭头 */
.fold-arrow {
  display: inline-block;
  margin-left: 12rpx;
  color: #8b95a5;
  font-size: 24rpx;
  transition: transform 0.2s ease;
}

.fold-arrow.expanded {
  transform: rotate(180deg);
}

/* 头部点击反馈 */
.result-header:active {
  background: rgba(0, 212, 255, 0.06);
}
```

要点：
- `.result-header` 已有 `background: rgba(0, 212, 255, 0.03)`（第 52 行），`:active` 选择器在点击瞬间叠加更深背景。
- `.fold-arrow` 的旋转过渡只作用于箭头本身，不涉及股票列表高度动画（YAGNI）。

- [ ] **Step 2：手动验证（开发者工具）**

  1. 重新编译。
  2. 期望：
     - 折叠箭头颜色为浅灰（与"xx 只"中"只"字颜色一致）。
     - 点击卡片头部时背景短暂变深、箭头平滑旋转 180°。
     - 收起时箭头再平滑转回。

- [ ] **Step 3：commit**

```bash
git add miniapp/pages/result/result.wxss
git commit -m "style(result): 折叠箭头旋转过渡与卡片头点击反馈"
```

---

## Task 5：端到端回归

- [ ] **Step 1：手动跑一次完整流程**

  1. 杀掉小程序进程，重新进入。
  2. 进入"结果"页面：
     - 所有卡片默认全部收起 ✓
     - 顶部"今日结果"标题和"执行中提示"（若有）正常显示 ✓
     - 空状态/加载中文案在无结果时正常显示 ✓
  3. 展开任意一张卡片 → 跳到"策略"页 → 再切回"结果"页 → onShow 重新拉数据 → 所有卡片应再次回到全部收起状态（验证"不记忆"要求）✓
  4. 展开后点击股票项跳详情 → 返回 → 该卡片仍保持展开（页面实例未销毁），其它卡片不受影响 ✓
  5. 若 `running-tip` 有内容（手动触发一个策略执行），在折叠交互期间不应被破坏 ✓

- [ ] **Step 2（可选）：若上一步发现问题，回到对应 Task 修复并 amend / 新增 commit。**

- [ ] **Step 3：无问题则收尾，无需额外 commit。**

---

## Self-Review

- **Spec coverage：**
  - 改动文件范围（result.js/wxml/wxss）→ Task 1/2/3/4
  - 数据结构注入 `collapsed: true` → Task 1
  - WXML `bindtap`、箭头、`wx:if` → Task 2
  - JS `toggleCard` 动态键名 setData → Task 3
  - WXSS 箭头旋转 + `:active` 反馈 → Task 4
  - 边界（空状态/加载中/running-tip 不受影响、`onShow` 重置）→ Task 5 回归
  - "不在范围内"项（无一键全展、无高度动画、无 storage 持久化、无后端改动）→ 均未引入。✓
- **Placeholder scan：** 无 TBD/TODO/"类似 Task N"等占位文本，所有步骤都给出了具体代码或具体验证步骤。
- **Type consistency：** 方法名 `toggleCard`、字段 `collapsed`、CSS 类 `.fold-arrow`/`.fold-arrow.expanded` 在 Task 1-4 中一致使用。✓
