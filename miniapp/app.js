App({
  globalData: {
    baseUrl: 'http://localhost:8000',
    userInfo: null,
    userId: null,
    userPhone: null,
    userNickname: null
  },

  onLaunch() {
    this.restoreSession()
  },

  restoreSession() {
    const userId = wx.getStorageSync('userId')
    if (userId) {
      this.globalData.userId = userId
      this.globalData.userPhone = wx.getStorageSync('userPhone') || ''
      this.globalData.userNickname = wx.getStorageSync('userNickname') || ''
    }
  },

  checkLogin() {
    if (!this.globalData.userId) {
      wx.redirectTo({ url: '/pages/login/login' })
      return false
    }
    return true
  },

  logout() {
    this.globalData.userId = null
    this.globalData.userPhone = null
    this.globalData.userNickname = null
    wx.removeStorageSync('userId')
    wx.removeStorageSync('userPhone')
    wx.removeStorageSync('userNickname')
    wx.redirectTo({ url: '/pages/login/login' })
  }
})
