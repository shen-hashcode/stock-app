const app = getApp()

Page({
  data: {
    strategyId: null,
    results: [],
    selectedDate: ''
  },

  onLoad(options) {
    if (options.strategyId) {
      this.setData({ strategyId: options.strategyId })
      this.loadResults()
    }
  },

  loadResults() {
    const { strategyId } = this.data
    if (!strategyId) return

    wx.request({
      url: `${app.globalData.baseUrl}/api/results/${strategyId}`,
      success: (res) => {
        if (res.data.code === 0) {
          const results = res.data.data.map(item => ({
            ...item,
            stocks: JSON.parse(item.stocks_json || '[]')
          }))
          this.setData({ results })
        }
      }
    })
  },

  onDateChange(e) {
    this.setData({ selectedDate: e.detail.value })
    // TODO: 按日期筛选
  },

  goStockDetail(e) {
    const { code, market } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/stock/stock?code=${code}&market=${market}`
    })
  }
})
