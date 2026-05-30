App({
  globalData: {
    baseUrl: 'https://your-domain.com',
    userInfo: null,
    userId: null
  },
  onLaunch() {
    this.login()
  },
  login() {
    wx.login({
      success: (res) => {
        if (res.code) {
          wx.request({
            url: `${this.globalData.baseUrl}/api/users`,
            method: 'POST',
            data: {
              openid: res.code,
              nickname: ''
            },
            success: (resp) => {
              if (resp.data.code === 0) {
                this.globalData.userId = resp.data.data.id
              }
            }
          })
        }
      }
    })
  }
})
