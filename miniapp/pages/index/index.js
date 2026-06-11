const app = getApp()
const { get } = require('../../utils/request')

Page({
  data: {
    builtinStrategies: []
  },

  onShow() {
    if (!app.checkLogin()) return
    this.loadBuiltinStrategies()
  },

  loadBuiltinStrategies() {
    get('/api/strategies/builtin').then(res => {
      if (res.code === 0) {
        this.setData({ builtinStrategies: res.data })
      }
    })
  },

  selectStrategy(e) {
    wx.showModal({
      title: '热门策略',
      content: '热门策略由系统每日自动执行，是否前往结果页查看？',
      confirmText: '去看看',
      cancelText: '取消',
      success: (res) => {
        if (res.confirm) {
          wx.switchTab({ url: '/pages/result/result' })
        }
      }
    })
  }
})