const { post } = require('../../utils/request')
const app = getApp()

Page({
  data: {
    mode: 'login',
    phone: '',
    password: '',
    nickname: '',
    loading: false
  },

  switchMode(e) {
    this.setData({ mode: e.currentTarget.dataset.mode })
  },

  onPhoneInput(e) {
    this.setData({ phone: e.detail.value })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value })
  },

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value })
  },

  handleSubmit() {
    const { mode, phone, password, nickname, loading } = this.data
    if (loading) return

    if (!phone || phone.length !== 11) {
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    if (!password || password.length < 6) {
      wx.showToast({ title: '密码至少6位', icon: 'none' })
      return
    }

    const url = mode === 'login' ? '/api/login' : '/api/register'
    const data = mode === 'login'
      ? { phone, password }
      : { phone, password, nickname }

    this.setData({ loading: true })
    wx.showLoading({ title: mode === 'login' ? '登录中...' : '注册中...' })

    post(url, data).then(res => {
      wx.hideLoading()
      this.setData({ loading: false })
      if (res.code === 0) {
        app.globalData.userId = res.data.id
        app.globalData.userPhone = res.data.phone
        app.globalData.userNickname = res.data.nickname
        wx.setStorageSync('userId', res.data.id)
        wx.setStorageSync('userPhone', res.data.phone)
        wx.setStorageSync('userNickname', res.data.nickname || '')
        wx.switchTab({ url: '/pages/index/index' })
      } else {
        wx.showToast({ title: res.message || '操作失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      this.setData({ loading: false })
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})
