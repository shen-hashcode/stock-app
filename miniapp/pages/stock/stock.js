const { get } = require('../../utils/request')

Page({
  data: {
    code: '',
    market: '',
    stockInfo: null,
    loading: true
  },

  onLoad(options) {
    if (options.code) {
      this.setData({ code: options.code, market: options.market || 'sh' })
      this.loadStockInfo()
    }
  },

  loadStockInfo() {
    const { code, market } = this.data
    get(`/api/stock/${code}`, { market }).then(res => {
      if (res.code === 0) {
        this.setData({ stockInfo: res.data, loading: false })
      } else {
        this.setData({ loading: false })
        wx.showToast({ title: '获取股票信息失败', icon: 'none' })
      }
    }).catch(() => {
      this.setData({ loading: false })
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})
