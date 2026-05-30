const app = getApp()

Page({
  data: {
    builtinStrategies: [],
    customName: '',
    customDesc: ''
  },

  onLoad() {
    this.loadBuiltinStrategies()
  },

  loadBuiltinStrategies() {
    wx.request({
      url: `${app.globalData.baseUrl}/api/strategies/builtin`,
      success: (res) => {
        if (res.data.code === 0) {
          this.setData({ builtinStrategies: res.data.data })
        }
      }
    })
  },

  selectStrategy(e) {
    const key = e.currentTarget.dataset.key
    wx.navigateTo({
      url: `/pages/strategy/strategy?type=builtin&key=${key}`
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

    wx.showLoading({ title: 'AI生成中...' })

    wx.request({
      url: `${app.globalData.baseUrl}/api/strategies/custom?user_id=${app.globalData.userId}`,
      method: 'POST',
      data: {
        name: customName,
        description: customDesc
      },
      success: (res) => {
        wx.hideLoading()
        if (res.data.code === 0) {
          wx.showToast({ title: '创建成功', icon: 'success' })
          setTimeout(() => {
            wx.switchTab({ url: '/pages/strategy/strategy' })
          }, 1500)
        } else {
          wx.showToast({ title: '创建失败', icon: 'none' })
        }
      },
      fail: () => {
        wx.hideLoading()
        wx.showToast({ title: '网络错误', icon: 'none' })
      }
    })
  }
})
