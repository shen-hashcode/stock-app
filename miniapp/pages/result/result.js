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
    this.loadTodayResults()
    this.checkRunning()
  },

  loadTodayResults() {
    const userId = app.globalData.userId
    if (!userId) return

    this.setData({ loading: true })
    get(`/api/results/${userId}`).then(res => {
      if (res.code === 0) {
        this.setData({ results: res.data || [], loading: false })
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

  goStockDetail(e) {
    const { code, market } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/stock/stock?code=${code}&market=${market}`
    })
  }
})
