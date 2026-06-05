# 结果页折叠功能设计

日期：2026-06-05
作者：bruce

## 背景

`miniapp/pages/result/` 当前会平铺展示当天所有策略命中的股票。当多个策略同时执行、每个策略命中几十只股票时，页面变得很长，用户难以快速浏览策略汇总。需要在结果页加入折叠功能，让用户先看到策略名+命中数量，再按需展开查看具体股票。

## 需求

- 折叠粒度：以每张策略卡片（result-card）为单位，折叠该卡片下的股票列表。
- 默认状态：进入页面时所有策略卡片下的股票列表**全部收起**，只显示策略名和命中数量。
- 状态记忆：不持久化、不跨会话记忆。每次进入页面都恢复为默认全部收起。同一会话内的展开/收起状态只在当前页面实例存活期间保留（页面销毁后重新进入即重置）。
- 交互方式：点击整个卡片头部区域（`result-header`）切换该卡片的展开/收起状态。
- 范围：仅前端小程序改动，后端 API 和数据结构无改动。

## 设计

### 改动文件

- `miniapp/pages/result/result.js`
- `miniapp/pages/result/result.wxml`
- `miniapp/pages/result/result.wxss`

后端、其他页面、`utils/` 均无改动。

### 数据结构

在 `loadTodayResults()` 拿到接口返回的 `res.data` 后，给每条 result 注入一个本地 UI 字段：

```js
const results = (res.data || []).map(r => ({ ...r, collapsed: true }))
this.setData({ results, loading: false })
```

`collapsed` 字段仅存在于小程序内存中，不写入 storage，不发回后端。

### WXML 改动

`result-header` 加上点击事件，并在右侧追加一个折叠箭头指示器：

```xml
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
  <!-- 原 stock-item 循环不变 -->
</view>
```

- `wx:for` 在外层 `result-card` 上，`{{index}}` 即该卡片在 `results` 数组中的下标。
- `stock-list` 整块用 `wx:if` 控制显隐；收起时 DOM 被销毁，不参与渲染。

### JS 改动

新增切换方法：

```js
toggleCard(e) {
  const i = e.currentTarget.dataset.index
  const key = `results[${i}].collapsed`
  this.setData({ [key]: !this.data.results[i].collapsed })
}
```

用动态键名局部更新，避免整张列表重渲。

### WXSS 改动

新增样式：

```css
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

.result-header {
  /* 已有样式不变，仅追加点击反馈 */
}

.result-header:active {
  background: rgba(0, 212, 255, 0.06);
}
```

`.result-header` 原有 `background: rgba(0, 212, 255, 0.03)` 保留；`:active` 选择器在点击瞬间叠加更深的背景作为反馈。

## 边界情况

- **空状态/加载中**：`empty-state`、`running-tip` 区块的逻辑不变，不参与折叠。
- **结果为 0 只的策略**：仍展示卡片头部，展开后 `stock-list` 内部循环为空 — 视觉上与现状一致（现状本就如此）。
- **后端返回新增字段**：注入 `collapsed` 用对象展开 `{ ...r, collapsed: true }`，不会覆盖后端字段。
- **刷新/重新进入页面**：`onShow` → `loadTodayResults` 重新拉数据，所有 `collapsed` 重置为 `true`，符合"不记忆"要求。

## 不在范围内

- 不做"一键全部展开/全部收起"按钮。
- 不做折叠动画（高度过渡），仅箭头旋转过渡。小程序对动态高度动画支持成本较高，YAGNI。
- 不持久化到 storage。
- 后端无任何改动。
