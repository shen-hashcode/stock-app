const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    strategies: [],
    customName: '',
    customDesc: '',
    paying: false
  },

  onShow() {
    if (!app.checkLogin()) return
    this.loadStrategies()
  },

  loadStrategies() {
    if (!app.globalData.userId) return
    get(`/api/strategies/${app.globalData.userId}`).then(res => {
      if (res.code === 0) {
        this.setData({ strategies: res.data })
      }
    })
  },

  viewResult(e) {
    const id = e.currentTarget.dataset.id
    app.globalData.viewStrategyId = id
    wx.switchTab({
      url: '/pages/result/result'
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

    if (this.data.paying) return

    this.setData({ paying: true })
    wx.showLoading({ title: '创建中...' })

    post(`/api/strategies/custom?user_id=${app.globalData.userId}`, {
      name: customName,
      description: customDesc
    }).then(res => {
      wx.hideLoading()
      if (res.code === 0) {
        const data = res.data || {}
        if (data.payment_params) {
          const params = data.payment_params
          wx.requestPayment({
            timeStamp: params.timeStamp,
            nonceStr: params.nonceStr,
            package: params.package,
            signType: params.signType,
            paySign: params.paySign,
            success: () => {
              this.pollStrategyOrder(data.order_no)
            },
            fail: (err) => {
              console.error('wx.requestPayment 失败:', JSON.stringify(err))
              this.setData({ paying: false })
              const msg = (err && err.errMsg) || '支付失败'
              wx.showToast({ title: msg, icon: 'none', duration: 3000 })
            }
          })
        } else {
          this.setData({ paying: false })
          wx.showToast({ title: '创建成功', icon: 'success' })
          this.setData({ customName: '', customDesc: '' })
          this.loadStrategies()
        }
      } else if (res.code === 3) {
        this.setData({ paying: false })
        wx.showModal({
          title: '配额已满',
          content: res.message || '当前套餐策略数量已达上限',
          confirmText: '升级套餐',
          cancelText: '知道了',
          success: (modalRes) => {
            if (modalRes.confirm) {
              wx.navigateTo({ url: '/pages/subscribe/subscribe?package_id=2' })
            }
          }
        })
      } else {
        this.setData({ paying: false })
        wx.showToast({ title: res.message || '创建失败', icon: 'none' })
      }
    }).catch(() => {
      wx.hideLoading()
      this.setData({ paying: false })
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  },

  pollStrategyOrder(orderNo) {
    let retries = 0
    const maxRetries = 10

    const check = () => {
      get(`/api/subscription/order/${orderNo}?user_id=${app.globalData.userId}`).then(res => {
        if (res.code === 0 && res.data.status === 'paid') {
          this.setData({ paying: false, customName: '', customDesc: '' })
          wx.showToast({ title: '订阅成功', icon: 'success' })
          this.loadStrategies()
          return
        }
        if (retries < maxRetries) {
          retries++
          setTimeout(check, 1500)
        } else {
          this.setData({ paying: false })
          wx.showToast({ title: '支付确认中，请稍后刷新', icon: 'none' })
        }
      }).catch(() => {
        if (retries < maxRetries) {
          retries++
          setTimeout(check, 1500)
        } else {
          this.setData({ paying: false })
        }
      })
    }

    check()
  }
})