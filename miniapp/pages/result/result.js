const app = getApp()
const { get } = require('../../utils/request')

Page({
  data: {
    results: [],
    loading: false
  },

  onShow() {
    if (!app.checkLogin()) return
    this.loadTodayResults()
  },

  loadTodayResults() {
    const userId = app.globalData.userId
    if (!userId) return

    this.setData({ loading: true })
    get(`/api/results/today/${userId}`).then(res => {
      if (res.code === 0) {
        this.setData({ results: res.data || [], loading: false })
      } else {
        this.setData({ loading: false })
      }
    }).catch(() => {
      this.setData({ loading: false })
    })
  },

  goStockDetail(e) {
    const { code, market } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/stock/stock?code=${code}&market=${market}`
    })
  }
})