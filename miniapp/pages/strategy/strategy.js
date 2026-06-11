const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    strategies: [],
    customName: '',
    customDesc: ''
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

  viewResult(e) {
    const id = e.currentTarget.dataset.id
    app.globalData.viewStrategyId = id
    wx.switchTab({
      url: '/pages/result/result'
    })
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

    wx.showLoading({ title: '生成中...' })

    post(`/api/strategies/custom?user_id=${app.globalData.userId}`, {
      name: customName,
      description: customDesc
    }).then(res => {
      wx.hideLoading()
      if (res.code === 0) {
        wx.showToast({ title: '创建成功', icon: 'success' })
        this.setData({ customName: '', customDesc: '' })
        this.loadStrategies()
      } else if (res.code === 2) {
        wx.showModal({
          title: '需要订阅',
          content: '请先订阅套餐后再创建自定义策略',
          confirmText: '去订阅',
          success: (modalRes) => {
            if (modalRes.confirm) {
              wx.navigateTo({ url: '/pages/subscribe/subscribe' })
            }
          }
        })
      } else if (res.code === 3) {
        wx.showModal({
          title: '配额已满',
          content: res.message || '当前套餐策略数量已达上限',
          confirmText: '升级套餐',
          cancelText: '知道了',
          success: (modalRes) => {
            if (modalRes.confirm) {
              wx.navigateTo({ url: '/pages/subscribe/subscribe' })
            }
          }
        })
      } else {
        wx.showToast({ title: res.message || '创建失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})