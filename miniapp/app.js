App({
  globalData: {
    baseUrl: 'http://localhost:8000',
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
          const { post } = require('./utils/request')
          post('/api/users', {
            openid: res.code,
            nickname: ''
          }).then(resp => {
            if (resp.code === 0) {
              this.globalData.userId = resp.data.id
              console.log('登录成功，用户ID:', this.globalData.userId)
            }
          })
        }
      }
    })
  }
})
