const app = getApp()
const { get } = require('../../utils/request')

Page({
  data: {
    strategies: []
  },

  onShow() {
    if (!app.checkLogin()) return
    this.loadStrategies()
  },

  loadStrategies() {
    if (!app.globalData.userId) return
    get(`/api/strategies/${app.globalData.userId}`).then(res => {
      if (res.code === 0) {
        this.setData({ strategies: res.data })
      }
    })
  },

  goCreate() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  viewResult(e) {
    const id = e.currentTarget.dataset.id
    app.globalData.viewStrategyId = id
    wx.switchTab({
      url: '/pages/result/result'
    })
  }
})