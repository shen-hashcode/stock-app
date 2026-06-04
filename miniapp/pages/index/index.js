const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    builtinStrategies: [],
    userStrategies: [],
    customName: '',
    customDesc: '',
    runningKey: ''
  },

  onShow() {
    if (!app.checkLogin()) return
    this.loadBuiltinStrategies()
    this.loadUserStrategies()
  },

  loadBuiltinStrategies() {
    get('/api/strategies/builtin').then(res => {
      if (res.code === 0) {
        this.setData({ builtinStrategies: res.data })
      }
    })
  },

  loadUserStrategies() {
    const userId = app.globalData.userId
    if (!userId) return
    get(`/api/strategies/${userId}`).then(res => {
      if (res.code === 0) {
        this.setData({ userStrategies: res.data || [] })
      }
    })
  },

  selectStrategy(e) {
    const key = e.currentTarget.dataset.key
    if (this.data.runningKey) return

    this.setData({ runningKey: key })
    wx.showLoading({ title: '查询中...' })

    post(`/api/strategies/builtin/${key}/run`).then(res => {
      wx.hideLoading()
      this.setData({ runningKey: '' })
      if (res.code === 0) {
        if (res.data.status === 'completed') {
          wx.switchTab({ url: '/pages/result/result' })
        } else {
          wx.showToast({ title: '策略执行中，请稍后查看结果', icon: 'none' })
        }
      } else {
        wx.showToast({ title: '执行失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      this.setData({ runningKey: '' })
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  },

  selectUserStrategy(e) {
    const id = e.currentTarget.dataset.id
    if (this.data.runningKey) return

    const runKey = 'user_' + id
    this.setData({ runningKey: runKey })
    wx.showLoading({ title: '查询中...' })

    post(`/api/strategies/${id}/run`).then(res => {
      wx.hideLoading()
      this.setData({ runningKey: '' })
      if (res.code === 0) {
        if (res.data.status === 'completed') {
          wx.switchTab({ url: '/pages/result/result' })
        } else {
          wx.showToast({ title: '策略执行中，请稍后查看结果', icon: 'none' })
        }
      } else {
        wx.showToast({ title: '执行失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      this.setData({ runningKey: '' })
      wx.showToast({ title: '网络错误', icon: 'none' })
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
        this.loadUserStrategies()
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