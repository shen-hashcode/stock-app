const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    strategies: [],
    showResult: false,
    resultCount: 0,
    resultStocks: []
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

  toggleStrategy(e) {
    const id = e.currentTarget.dataset.id
    const active = e.detail.value
  },

  runStrategy(e) {
    const id = e.currentTarget.dataset.id
    wx.showLoading({ title: '筛选中...' })
    post(`/api/strategies/${id}/run`, null, { timeout: 120000 }).then(res => {
      wx.hideLoading()
      if (res.code === 0) {
        this.setData({
          showResult: true,
          resultCount: res.data.count,
          resultStocks: res.data.stocks
        })
      } else {
        wx.showToast({ title: '执行失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  },

  viewResult(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/result/result?strategyId=${id}`
    })
  },

  closeModal() {
    this.setData({ showResult: false })
  }
})
