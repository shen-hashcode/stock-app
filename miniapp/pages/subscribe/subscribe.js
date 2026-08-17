const app = getApp()
const { get, post } = require('../../utils/request')

Page({
  data: {
    packages: [],
    subscription: null,
    loading: true,
    paying: false,
    filterPackageId: null
  },

  onLoad(options) {
    if (options && options.package_id) {
      this.setData({ filterPackageId: parseInt(options.package_id, 10) })
    }
  },

  onShow() {
    if (!app.checkLogin()) return
    this.loadData()
  },

  loadData() {
    this.setData({ loading: true })
    Promise.all([
      get('/api/subscription/packages'),
      get(`/api/subscription/status?user_id=${app.globalData.userId}`)
    ]).then(([pkgRes, statusRes]) => {
      let packages = pkgRes.code === 0 ? pkgRes.data : []
      if (this.data.filterPackageId) {
        packages = packages.filter(p => p.id === this.data.filterPackageId)
      }
      this.setData({
        packages,
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

    if (!app.globalData.userId) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      wx.redirectTo({ url: '/pages/login/login' })
      return
    }

    const packageId = e.currentTarget.dataset.id

    this.setData({ paying: true })
    wx.showLoading({ title: '创建订单...' })

    post(`/api/subscription/create_order?user_id=${app.globalData.userId}`, {
      package_id: packageId
    }).then(res => {
      wx.hideLoading()
      if (res.code !== 0) {
        this.setData({ paying: false })
        wx.showToast({ title: res.message || '创建订单失败', icon: 'none', duration: 3000 })
        return
      }

      const params = res.data.payment_params
      const orderNo = res.data.order_no

      console.log('wx.requestPayment params:', JSON.stringify(params))
      wx.requestPayment({
        timeStamp: params.timeStamp,
        nonceStr: params.nonceStr,
        package: params.package,
        signType: params.signType,
        paySign: params.paySign,
        success: () => {
          this.pollOrderStatus(orderNo, false)
        },
        fail: (err) => {
          console.error('wx.requestPayment 失败:', JSON.stringify(err))
          wx.showLoading({ title: '重新获取支付信息...' })
          this.pollOrderStatus(orderNo, true)
        }
      })
    }).catch((err) => {
      wx.hideLoading()
      this.setData({ paying: false })
      console.error('创建订单失败:', err)
      wx.showToast({ title: '网络错误，请检查是否开启了"不校验合法域名"', icon: 'none', duration: 3000 })
    })
  },

  pollOrderStatus(orderNo, retryPayment) {
    let retries = 0
    const maxRetries = 10

    const check = () => {
      get(`/api/subscription/order/${orderNo}?user_id=${app.globalData.userId}`).then(res => {
        if (res.code === 0 && res.data.status === 'paid') {
          this.setData({ paying: false })
          wx.showToast({ title: '订阅成功', icon: 'success' })
          this.loadData()
          return
        }

        // 如果要求重试支付且有可用的支付参数，重新拉起微信支付
        if (retryPayment && res.code === 0 && res.data.payment_params) {
          const params = res.data.payment_params

          wx.requestPayment({
            timeStamp: params.timeStamp,
            nonceStr: params.nonceStr,
            package: params.package,
            signType: params.signType,
            paySign: params.paySign,
            success: () => {
              this.pollOrderStatus(orderNo, false)
            },
            fail: (err) => {
              this.setData({ paying: false })
              const msg = (err && err.errMsg) || '支付失败'
              wx.showToast({ title: msg, icon: 'none', duration: 3000 })
            }
          })
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
