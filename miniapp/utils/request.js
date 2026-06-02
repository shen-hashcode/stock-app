const app = getApp()

function request(options) {
  const { url, method = 'GET', data, timeout = 10000 } = options
  const fullUrl = /^https?:\/\//.test(url) ? url : app.globalData.baseUrl + url

  return new Promise((resolve, reject) => {
    wx.request({
      url: fullUrl,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        'X-User-Id': app.globalData.userId || ''
      },
      timeout,
      success: (res) => {
        if (res.statusCode === 401) {
          app.globalData.userId = null
          wx.removeStorageSync('userId')
          wx.redirectTo({ url: '/pages/login/login' })
          reject(res)
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(res)
        }
      },
      fail: (err) => {
        wx.showToast({ title: '网络请求失败', icon: 'none' })
        reject(err)
      }
    })
  })
}

module.exports = {
  get: (url, data, options) => request({ url, method: 'GET', data, ...options }),
  post: (url, data, options) => request({ url, method: 'POST', data, ...options }),
  put: (url, data, options) => request({ url, method: 'PUT', data, ...options }),
  del: (url, data, options) => request({ url, method: 'DELETE', data, ...options })
}
