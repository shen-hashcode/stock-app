const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    builtinStrategies: [],
    customName: '',
    customDesc: '',
    showResult: false,
    resultCount: 0,
    resultStocks: [],
    runningKey: '',
    polling: false
  },

  _pollTimer: null,

  onShow() {
    if (!app.checkLogin()) return
    this.loadBuiltinStrategies()
  },

  onHide() {
    this.stopPolling()
  },

  onUnload() {
    this.stopPolling()
  },

  loadBuiltinStrategies() {
    get('/api/strategies/builtin').then(res => {
      if (res.code === 0) {
        this.setData({ builtinStrategies: res.data })
      }
    })
  },

  selectStrategy(e) {
    const key = e.currentTarget.dataset.key
    if (this.data.polling) return

    this.setData({ runningKey: key, polling: true })
    wx.showLoading({ title: '策略执行中...' })

    post(`/api/strategies/builtin/${key}/run`).then(res => {
      if (res.code === 0) {
        if (res.data.status === 'completed') {
          this.onStrategyComplete(res.data)
        } else {
          this.startPolling(key)
        }
      } else {
        this.onStrategyError('执行失败')
      }
    }).catch(() => {
      this.onStrategyError('网络错误')
    })
  },

  startPolling(key) {
    this._pollTimer = setInterval(() => {
      post(`/api/strategies/builtin/${key}/run`).then(res => {
        if (res.code === 0 && res.data.status === 'completed') {
          this.onStrategyComplete(res.data)
        }
      }).catch(() => {})
    }, 3000)
  },

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer)
      this._pollTimer = null
    }
    this.setData({ polling: false })
  },

  onStrategyComplete(data) {
    this.stopPolling()
    wx.hideLoading()
    this.setData({
      showResult: true,
      resultCount: data.count,
      resultStocks: data.stocks
    })
  },

  onStrategyError(msg) {
    this.stopPolling()
    wx.hideLoading()
    this.setData({ runningKey: '' })
    wx.showToast({ title: msg, icon: 'none' })
  },

  closeModal() {
    this.setData({ showResult: false, runningKey: '' })
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

    post(`/api/strategies/custom?user_id=${app.globalData.userId}`, {
      name: customName,
      description: customDesc
    }).then(res => {
      wx.hideLoading()
      if (res.code === 0) {
        wx.showToast({ title: '创建成功', icon: 'success' })
        setTimeout(() => {
          wx.switchTab({ url: '/pages/strategy/strategy' })
        }, 1500)
      } else {
        wx.showToast({ title: '创建失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})
