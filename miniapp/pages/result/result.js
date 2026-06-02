const { get } = require('../../utils/request')

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
    get(`/api/results/${strategyId}`).then(res => {
      if (res.code === 0) {
        const results = res.data.map(item => ({
          ...item,
          stocks: JSON.parse(item.stocks_json || '[]')
        }))
        this.setData({ results })
      }
    })
  },

  onDateChange(e) {
    this.setData({ selectedDate: e.detail.value })
  },

  goStockDetail(e) {
    const { code, market } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/stock/stock?code=${code}&market=${market}`
    })
  }
})
