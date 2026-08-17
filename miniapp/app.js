App({
  globalData: {
    baseUrl: 'https://7d10ca8e.r25.cpolar.top',
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