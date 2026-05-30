const app = getApp()

Page({
  data: {
    strategies: [],
    showResult: false,
    resultCount: 0,
    resultStocks: []
  },

  onShow() {
    this.loadStrategies()
  },

  loadStrategies() {
    if (!app.globalData.userId) return
    
    wx.request({
      url: `${app.globalData.baseUrl}/api/strategies/${app.globalData.userId}`,
      success: (res) => {
        if (res.data.code === 0) {
          this.setData({ strategies: res.data.data })
        }
      }
    })
  },

  goCreate() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  toggleStrategy(e) {
    const id = e.currentTarget.dataset.id
    const active = e.detail.value
    // TODO: 调用API更新策略状态
  },

  runStrategy(e) {
    const id = e.currentTarget.dataset.id
    wx.showLoading({ title: '筛选中...' })
    
    wx.request({
      url: `${app.globalData.baseUrl}/api/strategies/${id}/run`,
      method: 'POST',
      success: (res) => {
        wx.hideLoading()
        if (res.data.code === 0) {
          this.setData({
            showResult: true,
            resultCount: res.data.data.count,
            resultStocks: res.data.data.stocks
          })
        } else {
          wx.showToast({ title: '执行失败', icon: 'none' })
        }
      },
      fail: () => {
        wx.hideLoading()
        wx.showToast({ title: '网络错误', icon: 'none' })
      }
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
