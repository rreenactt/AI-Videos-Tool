import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8001'

export default function App() {
  const nav = useNavigate()
  const [home, setHome] = useState({ counts: {prompts:0, images:0, videos:0, projects:0}, lists: {prompts:[], images:[], videos:[], projects:[]} })
  const [error, setError] = useState('')
  const [showModeSelect, setShowModeSelect] = useState(false)
  const [selectedMode, setSelectedMode] = useState('story')

  const refreshHome = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/home`)
      if (!res.ok) throw new Error('홈 데이터 로드 실패')
      const data = await res.json()
      setHome(data)
    } catch {}
  }

  useEffect(() => { refreshHome() }, [])

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

      <header className="header">
        <div className="brand">
          <img src="/auto-shorts-logo.png" alt="AUTO Shorts" style={{width:120,height:120,objectFit:'contain'}} />
          <div style={{fontWeight:700}}>AIVideos · Projects</div>
        </div>
        <div className="actions">
          <button className="btn primary" onClick={startProject}>프로젝트 시작하기</button>
        </div>
      </header>

      <div className="shell">
        {/* Projects grid */}
        <div>
          <div className="section-title">프로젝트 ({home.counts.projects || 0})</div>
          <div className="grid">
            <button className="new-tile" onClick={startProject}>+ 새 프로젝트</button>
            {home.lists.projects?.length ? home.lists.projects.map(p => (
              <div className="card project-card" key={p.id} onClick={()=>nav(`/project/${p.id}`)} style={{cursor:'pointer'}}>
                <div className="project-title">{p.title}</div>
                <div className="project-meta">모드: {p.mode === 'fusion' ? '퓨전' : '스토리'}</div>
                <div className="project-meta">생성일: {p.createdAt || '-'}</div>
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
            <div className="list">
              {home.lists.videos?.length ? home.lists.videos.map((v,i)=> (
                <div className="item" key={i}><a href={v} target="_blank" rel="noreferrer" style={{color:'#e2e8f0'}}>{v}</a></div>
              )) : <div className="item" style={{opacity:.7}}>아직 영상이 없습니다.</div>}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

