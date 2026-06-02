const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    builtinStrategies: [],
    customName: '',
    customDesc: '',
    showResult: false,
    resultCount: 0,
    resultStocks: [],
    runningKey: ''
  },

  onLoad() {
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
    const key = e.currentTarget.dataset.key
    this.setData({ runningKey: key })
    wx.showLoading({ title: '筛选中...' })

    post(`/api/strategies/builtin/${key}/run?stock_limit=200`, null, { timeout: 120000 }).then(res => {
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

  closeModal() {
    this.setData({ showResult: false, runningKey: '' })
  },

  onNameInput(e) {
    this.setData({ customName: e.detail.value })
  },

  onDescInput(e) {
    this.setData({ customDesc: e.detail.value })
  },

  createCustomStrategy() {
    const { customName, customDesc } = this.data

    if (!customName || !customDesc) {
      wx.showToast({ title: '请填写完整信息', icon: 'none' })
      return
    }

    wx.showLoading({ title: 'AI生成中...' })

    post(`/api/strategies/custom?user_id=${app.globalData.userId}`, {
      name: customName,
      description: customDesc
    }).then(res => {
      wx.hideLoading()
      if (res.code === 0) {
        wx.showToast({ title: '创建成功', icon: 'success' })
        setTimeout(() => {
          wx.switchTab({ url: '/pages/strategy/strategy' })
        }, 1500)
      } else {
        wx.showToast({ title: '创建失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})
