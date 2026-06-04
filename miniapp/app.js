App({
  globalData: {
    baseUrl: 'http://121.40.124.210:8000',
    userId: null
  },

  onLaunch() {
    this.restoreSession()
  },

  restoreSession() {
    const userId = wx.getStorageSync('userId')
    if (userId) {
      this.globalData.userId = userId
    }
  },

  checkLogin() {
    if (!this.globalData.userId) {
      wx.redirectTo({ url: '/pages/login/login' })
      return false
    }
    return true
  }
})