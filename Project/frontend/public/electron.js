const { app, BrowserWindow, Menu, dialog, shell, ipcMain } = require('electron')
const { autoUpdater } = require('electron-updater')
const path = require('path')
const isDev = process.env.NODE_ENV === 'development'

// 자동 업데이트 설정
autoUpdater.checkForUpdatesAndNotify()

let mainWindow

function createWindow() {
  // 메인 윈도우 생성
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, 'auto-shorts.png'),
    titleBarStyle: 'default',
    show: false
  })

  // 개발 모드에서는 localhost, 프로덕션에서는 빌드된 파일
  const startUrl = isDev 
    ? 'http://localhost:5173' 
    : `file://${path.join(__dirname, '../dist/index.html')}`
  
  mainWindow.loadURL(startUrl)

  // 윈도우가 준비되면 표시
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
    
    // 개발 모드에서는 DevTools 자동 열기
    if (isDev) {
      mainWindow.webContents.openDevTools()
    }
  })

  // 윈도우가 닫힐 때
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // 외부 링크는 기본 브라우저에서 열기
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

// 앱 메뉴 설정
function createMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'New Project',
          accelerator: 'CmdOrCtrl+N',
          click: () => {
            mainWindow.webContents.send('menu-new-project')
          }
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.quit()
          }
        }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About AUTO Shorts',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About AUTO Shorts',
              message: 'AUTO Shorts Desktop',
              detail: `Version: ${app.getVersion()}\nAI 기반 자동 쇼츠 비디오 생성 프로그램`
            })
          }
        },
        {
          label: 'Check for Updates',
          click: () => {
            autoUpdater.checkForUpdatesAndNotify()
          }
        }
      ]
    }
  ]

  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}

// 앱 이벤트 핸들러
app.whenReady().then(() => {
  createWindow()
  createMenu()
  
  // 자동 업데이트 체크
  setTimeout(() => {
    autoUpdater.checkForUpdatesAndNotify()
  }, 3000)
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

// 자동 업데이트 이벤트 핸들러
autoUpdater.on('checking-for-update', () => {
  console.log('업데이트 확인 중...')
})

autoUpdater.on('update-available', (info) => {
  console.log('업데이트 사용 가능:', info.version)
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: '업데이트 사용 가능',
    message: `새 버전 ${info.version}이 사용 가능합니다.`,
    detail: '업데이트를 다운로드하고 설치하시겠습니까?',
    buttons: ['나중에', '업데이트']
  }).then((result) => {
    if (result.response === 1) {
      autoUpdater.downloadUpdate()
    }
  })
})

autoUpdater.on('update-not-available', (info) => {
  console.log('최신 버전입니다:', info.version)
})

autoUpdater.on('error', (err) => {
  console.error('업데이트 오류:', err)
})

autoUpdater.on('download-progress', (progressObj) => {
  let log_message = "다운로드 속도: " + progressObj.bytesPerSecond
  log_message = log_message + ' - 다운로드 ' + progressObj.percent + '%'
  log_message = log_message + ' (' + progressObj.transferred + "/" + progressObj.total + ')'
  console.log(log_message)
  
  // 프론트엔드에 진행상황 전송
  mainWindow.webContents.send('update-progress', progressObj)
})

autoUpdater.on('update-downloaded', (info) => {
  console.log('업데이트 다운로드 완료')
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: '업데이트 준비 완료',
    message: '업데이트가 다운로드되었습니다.',
    detail: '애플리케이션을 재시작하여 업데이트를 적용하시겠습니까?',
    buttons: ['나중에', '지금 재시작']
  }).then((result) => {
    if (result.response === 1) {
      autoUpdater.quitAndInstall()
    }
  })
})

// IPC 핸들러
ipcMain.handle('get-app-version', () => {
  return app.getVersion()
})

ipcMain.handle('check-for-updates', () => {
  autoUpdater.checkForUpdatesAndNotify()
})

ipcMain.handle('show-save-dialog', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options)
  return result
})

ipcMain.handle('show-open-dialog', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options)
  return result
})
