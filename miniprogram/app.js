// app.js —— 市场日历小程序入口
App({
  globalData: {
    // 云开发环境 ID：填入你自己的云开发环境后，增量同步才会生效
    // 未配置时小程序完全使用内置离线数据包，功能不受影响
    cloudEnv: '',
    useCloud: false
  },

  onLaunch() {
    const info = wx.getSystemInfoSync ? wx.getSystemInfoSync() : {}
    this.globalData.safeBottom = (info.screenHeight || 0) - (info.safeArea ? info.safeArea.bottom : 0)
    this.globalData.statusBarHeight = info.statusBarHeight || 20
  }
})
