const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    builtinStrategies: [],
    userStrategies: [],
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
    this.loadUserStrategies()
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
    if (this.data.polling) return

    this.setData({ runningKey: key, polling: true })
    wx.showLoading({ title: '策略执行中...' })

    post(`/api/strategies/builtin/${key}/run`).then(res => {
      if (res.code === 0) {
        if (res.data.status === 'completed') {
          this.onStrategyComplete(res.data)
        } else {
          this.startPolling(key, 'builtin')
        }
      } else {
        this.onStrategyError('执行失败')
      }
    }).catch(() => {
      this.onStrategyError('网络错误')
    })
  },

  selectUserStrategy(e) {
    const id = e.currentTarget.dataset.id
    if (this.data.polling) return

    const runKey = 'user_' + id
    this.setData({ runningKey: runKey, polling: true })
    wx.showLoading({ title: '策略执行中...' })

    post(`/api/strategies/${id}/run`).then(res => {
      if (res.code === 0) {
        if (res.data.status === 'completed') {
          this.onStrategyComplete(res.data)
        } else {
          this.startPolling(id, 'user')
        }
      } else {
        this.onStrategyError('执行失败')
      }
    }).catch(() => {
      this.onStrategyError('网络错误')
    })
  },

  startPolling(key, type) {
    this._pollTimer = setInterval(() => {
      const url = type === 'builtin'
        ? `/api/strategies/builtin/${key}/run`
        : `/api/strategies/${key}/run`
      post(url).then(res => {
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
      } else {
        wx.showToast({ title: '创建失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})