import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE || ''

// Electron API 사용 가능 여부 확인
const isElectron = typeof window !== 'undefined' && window.electronAPI

export default function App() {
  const nav = useNavigate()
  const [home, setHome] = useState({ counts: {prompts:0, images:0, videos:0, projects:0}, lists: {prompts:[], images:[], videos:[], projects:[]} })
  const [error, setError] = useState('')
  const [showModeSelect, setShowModeSelect] = useState(false)
  const [selectedMode, setSelectedMode] = useState('story')
  const [appVersion, setAppVersion] = useState('')
  const [updateProgress, setUpdateProgress] = useState(null)

  const refreshHome = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/home`)
      if (!res.ok) throw new Error('홈 데이터 로드 실패')
      const data = await res.json()
      setHome(data)
    } catch {}
  }

  useEffect(() => { 
    refreshHome()
    
    // Electron 환경에서 앱 버전 가져오기
    if (isElectron) {
      window.electronAPI.getAppVersion().then(version => {
        setAppVersion(version)
      })
      
      // 메뉴에서 새 프로젝트 생성 이벤트 리스너
      window.electronAPI.onMenuNewProject(() => {
        startProject()
      })
      
      // 업데이트 진행상황 리스너
      window.electronAPI.onUpdateProgress((event, progress) => {
        setUpdateProgress(progress)
      })
    }
  }, [])

  const startProject = async () => {
    setShowModeSelect(true)
  }

  const createProject = async (mode) => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '새 프로젝트', mode })
      })
      if (!res.ok) throw new Error('프로젝트 생성 실패')
      const meta = await res.json()
      await refreshHome()
      setShowModeSelect(false)
      nav(`/project/${meta.id}`)
    } catch (e) { setError(e?.message || '오류가 발생했습니다') }
  }

  return (
    <>
      {showModeSelect && (
        <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,.5)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}}>
          <div className="card" style={{padding:24,minWidth:400}}>
            <div className="section-title" style={{marginBottom:16}}>모드 선택</div>
            <div className="grid" style={{gridTemplateColumns:'1fr 1fr',gap:12,marginBottom:16}}>
              <button className={`card project-card ${selectedMode==='story'?'selected':''}`} onClick={()=>setSelectedMode('story')} style={{border:selectedMode==='story'?'2px solid #2563eb':'1px solid var(--border)',cursor:'pointer'}}>
                <div className="project-title">스토리 모드</div>
                <div className="project-meta">스토리 → 이미지 + TTS</div>
              </button>
              <button className={`card project-card ${selectedMode==='fusion'?'selected':''}`} onClick={()=>setSelectedMode('fusion')} style={{border:selectedMode==='fusion'?'2px solid #2563eb':'1px solid var(--border)',cursor:'pointer'}}>
                <div className="project-title">퓨전 모드</div>
                <div className="project-meta">비디오 합성/블렌딩</div>
              </button>
            </div>
            <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
              <button className="btn ghost" onClick={()=>setShowModeSelect(false)}>취소</button>
              <button className="btn primary" onClick={()=>createProject(selectedMode)}>생성</button>
            </div>
          </div>
        </div>
      )}

      <header className="header-logo">
        <img src="/auto-shorts.png" alt="AUTO Shorts" className="main-logo" />
        {isElectron && appVersion && (
          <div style={{position:'absolute', top:8, right:24, fontSize:12, color:'#6b7280'}}>
            Desktop v{appVersion}
          </div>
        )}
      </header>
      
      {/* 업데이트 진행상황 표시 */}
      {updateProgress && (
        <div style={{
          position:'fixed', top:0, left:0, right:0, 
          background:'#2563eb', color:'white', padding:'8px 16px', 
          fontSize:12, zIndex:9999, textAlign:'center'
        }}>
          업데이트 다운로드 중... {Math.round(updateProgress.percent)}%
          <div style={{
            width:'100%', height:2, background:'rgba(255,255,255,0.3)', 
            marginTop:4, borderRadius:1, overflow:'hidden'
          }}>
            <div style={{
              width:`${updateProgress.percent}%`, height:'100%', 
              background:'white', transition:'width 0.3s'
            }} />
          </div>
        </div>
      )}

      <div className="shell">
        {/* Projects grid */}
        <div>
          <div className="section-title">프로젝트 ({home.counts.projects || 0})</div>
          <div className="grid">
            <button className="new-tile" onClick={startProject}>+ 새 프로젝트</button>
            {home.lists.projects?.length ? home.lists.projects.map(p => (
              <div className="card project-card" key={p.id} onClick={()=>nav(`/project/${p.id}`)} style={{cursor:'pointer',overflow:'hidden',padding:0}}>
                {p.videoPath ? (
                  <div style={{width:'100%',height:140,background:'#000',position:'relative',overflow:'hidden'}}>
                    <video 
                      src={`${API_BASE}${p.videoPath}`}
                      style={{width:'100%',height:'100%',objectFit:'cover'}}
                      muted
                      playsInline
                      onMouseEnter={(e) => e.target.play()}
                      onMouseLeave={(e) => {e.target.pause(); e.target.currentTime = 0}}
                    />
                    <div style={{position:'absolute',top:8,right:8,background:'rgba(0,0,0,.7)',color:'#fff',padding:'4px 8px',borderRadius:6,fontSize:11,fontWeight:600}}>
                      🎬 영상
                    </div>
                  </div>
                ) : (
                  <div style={{width:'100%',height:140,background:'linear-gradient(135deg,#667eea 0%,#764ba2 100%)',display:'flex',alignItems:'center',justifyContent:'center',color:'#fff',fontSize:32,fontWeight:700}}>
                    {p.title?.[0] || '📁'}
                  </div>
                )}
                <div style={{padding:14}}>
                  <div className="project-title">{p.title}</div>
                  <div className="project-meta">모드: {p.mode === 'fusion' ? '퓨전' : '스토리'}</div>
                  {p.imageCount > 0 && <div className="project-meta">이미지: {p.imageCount}개</div>}
                  <div className="project-meta">생성일: {p.createdAt || '-'}</div>
                </div>
              </div>
            )) : null}
          </div>
          {error && <div className="section-title" style={{color:'#ef4444'}}>⚠ {error}</div>}
        </div>

        {/* Dark glass Videos panel */}
        <div className="sidebar">
          <div className="sidebar-inner">
            <h3>최근 영상</h3>
            <div className="kv">
              <div className="badge">videos {home.counts.videos}</div>
              <div className="badge">images {home.counts.images}</div>
              <div className="badge">prompts {home.counts.prompts}</div>
            </div>
            
            {/* 최신 영상을 쇼츠 스타일로 표시 */}
            {home.lists.videos?.length > 0 ? (
              <>
                <div className="shorts-player" style={{marginTop:16}}>
                  <div className="shorts-container">
                    <video 
                      src={home.lists.videos[home.lists.videos.length - 1]} 
                      controls 
                      loop
                      playsInline
                      className="shorts-video"
                    />
                    <div className="shorts-overlay">
                      <div className="shorts-title">최신 영상</div>
                      <div className="shorts-info">
                        {new Date().toLocaleDateString('ko-KR')}
                      </div>
                    </div>
                  </div>
                </div>
                
                {home.lists.videos.length > 1 && (
                  <div className="list" style={{marginTop:16}}>
                    <div style={{fontSize:12,color:'#94a3b8',marginBottom:8}}>이전 영상 목록</div>
                    {home.lists.videos.slice(0, -1).reverse().map((v,i)=> (
                      <div className="item" key={i}>
                        <a href={v} target="_blank" rel="noreferrer" style={{color:'#e2e8f0',fontSize:12}}>
                          영상 #{home.lists.videos.length - i - 1}
                        </a>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="list" style={{marginTop:16}}>
                <div className="item" style={{opacity:.7}}>아직 영상이 없습니다.</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

