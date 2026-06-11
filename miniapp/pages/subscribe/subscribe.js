const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    packages: [],
    subscription: null,
    loading: true,
    paying: false
  },

  onShow() {
    this.loadData()
  },

  loadData() {
    this.setData({ loading: true })
    Promise.all([
      get('/api/subscription/packages'),
      get(`/api/subscription/status?user_id=${app.globalData.userId}`)
    ]).then(([pkgRes, statusRes]) => {
      this.setData({
        packages: pkgRes.code === 0 ? pkgRes.data : [],
        subscription: statusRes.code === 0 ? statusRes.data : null,
        loading: false
      })
    }).catch(() => {
      this.setData({ loading: false })
      wx.showToast({ title: '加载失败', icon: 'none' })
    })
  },

  buyPackage(e) {
    if (this.data.paying) return
    const packageId = e.currentTarget.dataset.id

    this.setData({ paying: true })
    wx.showLoading({ title: '创建订单...' })

    post(`/api/subscription/create_order?user_id=${app.globalData.userId}`, {
      package_id: packageId
    }).then(res => {
      wx.hideLoading()
      if (res.code !== 0) {
        this.setData({ paying: false })
        wx.showToast({ title: res.message || '创建订单失败', icon: 'none' })
        return
      }

      const params = res.data.payment_params
      const orderNo = res.data.order_no

      if (res.data.mock) {
        post(`/api/subscription/mock_pay/${orderNo}?user_id=${app.globalData.userId}`).then(mockRes => {
          if (mockRes.code === 0) {
            this.setData({ paying: false })
            wx.showToast({ title: '订阅成功', icon: 'success' })
            this.loadData()
          } else {
            this.setData({ paying: false })
            wx.showToast({ title: mockRes.message || '支付失败', icon: 'none' })
          }
        }).catch(() => {
          this.setData({ paying: false })
          wx.showToast({ title: '网络错误', icon: 'none' })
        })
        return
      }

      wx.requestPayment({
        timeStamp: params.timeStamp,
        nonceStr: params.nonceStr,
        package: params.package,
        signType: params.signType,
        paySign: params.paySign,
        success: () => {
          this.pollOrderStatus(orderNo)
        },
        fail: () => {
          this.setData({ paying: false })
          wx.showToast({ title: '支付取消', icon: 'none' })
        }
      })
    }).catch(() => {
      wx.hideLoading()
      this.setData({ paying: false })
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  },

  pollOrderStatus(orderNo) {
    let retries = 0
    const maxRetries = 10

    const check = () => {
      get(`/api/subscription/order/${orderNo}?user_id=${app.globalData.userId}`).then(res => {
        if (res.code === 0 && res.data.status === 'paid') {
          this.setData({ paying: false })
          wx.showToast({ title: '订阅成功', icon: 'success' })
          this.loadData()
        } else if (retries < maxRetries) {
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
