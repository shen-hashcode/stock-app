const app = getApp()
const { get } = require('../../utils/request')

Page({
  data: {
    results: [],
    loading: false,
    runningStrategies: []
  },

  onShow() {
    if (!app.checkLogin()) return

    const strategyId = app.globalData.viewStrategyId
    if (strategyId) {
      app.globalData.viewStrategyId = null
      this.loadStrategyResults(strategyId)
    } else {
      this.loadTodayResults()
    }
    this.checkRunning()
  },

  loadStrategyResults(strategyId) {
    const userId = app.globalData.userId
    if (!userId) return

    this.setData({ loading: true })
    get(`/api/results/${userId}`).then(res => {
      if (res.code === 0) {
        const results = (res.data || [])
          .filter(r => r.strategy_id === strategyId)
          .map(r => ({ ...r, collapsed: true }))
        this.setData({ results, loading: false })
      } else {
        this.setData({ loading: false })
      }
    }).catch(() => {
      this.setData({ loading: false })
    })
  },

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

  checkRunning() {
    const userId = app.globalData.userId
    if (!userId) return
    get(`/api/strategies/running/${userId}`).then(res => {
      if (res.code === 0) {
        this.setData({ runningStrategies: res.data || [] })
      }
    })
  },

  toggleCard(e) {
    const i = e.currentTarget.dataset.index
    const key = `results[${i}].collapsed`
    this.setData({ [key]: !this.data.results[i].collapsed })
  },

  goStockDetail(e) {
    const { code, market } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/stock/stock?code=${code}&market=${market}`
    })
  }
})
