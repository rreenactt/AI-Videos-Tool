const { contextBridge, ipcRenderer } = require('electron')

// 안전한 API를 렌더러 프로세스에 노출
contextBridge.exposeInMainWorld('electronAPI', {
  // 앱 정보
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // 업데이트 관련
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  onUpdateProgress: (callback) => ipcRenderer.on('update-progress', callback),
  
  // 파일 다이얼로그
  showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
  
  // 메뉴 이벤트
  onMenuNewProject: (callback) => ipcRenderer.on('menu-new-project', callback),
  
  // 플랫폼 정보
  platform: process.platform,
  
  // 개발 모드 여부
  isDev: process.env.NODE_ENV === 'development'
})
