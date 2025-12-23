import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8001'

export default function Project(){
  const { id } = useParams()
  const nav = useNavigate()
  const [story, setStory] = useState('')
  const [title, setTitle] = useState('')
  const [minShots, setMinShots] = useState(2)
  const [prompts, setPrompts] = useState([])
  const [cuts, setCuts] = useState([])
  const [saved, setSaved] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [projectMode, setProjectMode] = useState('story')
  const [imageJobId, setImageJobId] = useState('')
  const [imageProgress, setImageProgress] = useState({status:'',progress:0,message:''})
  const [projectLoaded, setProjectLoaded] = useState(false)
  const [lastSavedDraft, setLastSavedDraft] = useState({title:'', story:'', minShots:2})

  const disabledGen = useMemo(() => loading || !story.trim(), [loading, story])
  const disabledImg = useMemo(() => loading || prompts.length === 0, [loading, prompts])

  useEffect(()=>{ 
    document.title = `Project · ${id}`
  }, [id])

  useEffect(() => {
    let active = true
    const loadProject = async () => {
      setProjectLoaded(false)
      try{
        const res = await fetch(`${API_BASE}/api/projects/${id}`)
        if(!res.ok) throw new Error('프로젝트 로드 실패')
        const data = await res.json()
        if(!active) return
        const state = data.state || {}
        setProjectMode(data.meta?.mode || 'story')
        setTitle(state.title ?? data.meta?.title ?? '')
        setStory(state.story ?? '')
        setMinShots(state.min_shots_per_scene ?? 2)
        setPrompts(state.prompts ?? [])
        setCuts(state.cuts ?? [])
        setSaved(state.saved_results ?? [])
        setImageProgress(state.image_progress ?? {status:'',progress:0,message:''})
        setImageJobId(state.image_job_id ?? '')
        setLastSavedDraft({
          title: state.title ?? data.meta?.title ?? '',
          story: state.story ?? '',
          minShots: state.min_shots_per_scene ?? 2
        })
        setError('')
        setProjectLoaded(true)
        setLoading(Boolean(state.image_job_id))
      }catch(e){
        if(!active) return
        setError(e?.message || '프로젝트 정보를 불러올 수 없습니다')
      }
    }
    loadProject()
    return () => { active = false }
  }, [id])

  // 이미지 생성 진행 상황 polling
  useEffect(() => {
    if(!imageJobId) return
    const interval = setInterval(async () => {
      try{
        const progRes = await fetch(`${API_BASE}/api/images/progress/${imageJobId}`)
        if(!progRes.ok) return
        const prog = await progRes.json()
        setImageProgress({status:prog.status,progress:prog.progress,message:prog.message||''})
        if(prog.status === 'completed'){
          clearInterval(interval)
          setLoading(false)
          setSaved(prog.results||[])
          setImageJobId('')
        }else if(prog.status === 'error'){
          clearInterval(interval)
          setLoading(false)
          setError(prog.error || '이미지 생성 실패')
          setImageJobId('')
        }
      }catch(e){ clearInterval(interval); setLoading(false); setImageJobId('') }
    }, 500)
    return () => clearInterval(interval)
  }, [imageJobId])

  const saveProjectState = useCallback(async (payload) => {
    if(!projectLoaded || !payload || Object.keys(payload).length === 0) return
    try{
      const res = await fetch(`${API_BASE}/api/projects/${id}`, {
        method: 'PATCH',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      })
      if(!res.ok) throw new Error('상태 저장 실패')
      const data = await res.json()
      if(data?.state){
        setLastSavedDraft({
          title: data.state.title ?? '',
          story: data.state.story ?? '',
          minShots: data.state.min_shots_per_scene ?? 1
        })
      }
    }catch(e){
      console.warn('프로젝트 상태 저장 실패', e)
    }
  }, [projectLoaded, id])

  useEffect(() => {
    if(!projectLoaded) return
    const nextMinShots = Number(minShots) || 1
    if(
      lastSavedDraft.title === title &&
      lastSavedDraft.story === story &&
      Number(lastSavedDraft.minShots) === nextMinShots
    ){
      return
    }
    const timer = setTimeout(() => {
      saveProjectState({ title, story, min_shots_per_scene: nextMinShots })
    }, 800)
    return () => clearTimeout(timer)
  }, [title, story, minShots, projectLoaded, lastSavedDraft, saveProjectState])

  const createStoryboard = async () => {
    setLoading(true); setError(''); setSaved([])
    try{
      const res = await fetch(`${API_BASE}/api/storyboard`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_id: id, story, title: title || undefined, min_shots_per_scene: Number(minShots)||1 })})
      if(!res.ok) throw new Error(`Storyboard failed (${res.status})`)
      const data = await res.json()
      setPrompts(data.prompts||[])
      setCuts(data.cuts||[])
      if(data.title) setTitle(data.title)
    }catch(e){ setError(e?.message || '오류가 발생했습니다') }
    finally{ setLoading(false) }
  }

  const generateImages = async () => {
    setLoading(true); setError(''); setImageProgress({status:'queued',progress:0,message:'작업 시작...'})
    try{
      const res = await fetch(`${API_BASE}/api/images`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_id: id, prompts, output_dir: 'Project/data/outputs' })})
      if(!res.ok) throw new Error(`Images failed (${res.status})`)
      const data = await res.json()
      setImageJobId(data.job_id)
    }catch(e){ setError(e?.message || '오류가 발생했습니다'); setLoading(false); setImageProgress({status:'',progress:0,message:''}) }
  }

  const handleResetSaved = async () => {
    setSaved([])
    await saveProjectState({ saved_results: [] })
  }

  const deleteProject = async () => {
    if(!confirm('정말 이 프로젝트를 삭제하시겠습니까?')) return
    try{
      const res = await fetch(`${API_BASE}/api/projects/${id}`, {method:'DELETE'})
      if(!res.ok) throw new Error('삭제 실패')
      nav('/')
    }catch(e){ setError(e?.message || '삭제 중 오류가 발생했습니다') }
  }

  return (
    <div className="shell" style={{paddingTop:24}}>
      <div>
        <div className="header-row" style={{marginBottom:8}}>
          <div>
            <div className="section-title">프로젝트 · {id}</div>
            <div className="help">모드: {projectMode === 'fusion' ? '퓨전 모드 (비디오 합성/블렌딩)' : '스토리 모드 (스토리 → 이미지 + TTS)'}</div>
          </div>
          <div style={{display:'flex', gap:8}}>
            <button className="btn ghost" onClick={deleteProject} style={{color:'#ef4444'}}>프로젝트 지우기</button>
            <Link className="btn ghost" to="/">홈으로</Link>
          </div>
        </div>

        {projectMode === 'story' ? (
          <>
            <div className="card project-card">
              <div className="grid" style={{gridTemplateColumns:'1fr 160px 160px'}}>
                <input className="input-sm" placeholder="작품 제목" value={title} onChange={e=>setTitle(e.target.value)} />
                <input className="input-sm" placeholder="최소 샷 수" type="number" min={1} max={8} value={minShots} onChange={e=>setMinShots(e.target.value)} />
                <button className="btn primary" onClick={createStoryboard} disabled={disabledGen}>{loading? '생성 중…':'스토리보드 생성'}</button>
              </div>
              <textarea className="input" placeholder="스토리를 입력하세요" value={story} onChange={e=>setStory(e.target.value)} />
              {error && <div className="help">⚠ {error}</div>}
            </div>

            {cuts.length>0 && (
              <div className="card project-card" style={{marginTop:12}}>
                <div className="section-title">컷별 요소 ({cuts.length}개)</div>
                <div className="list">
                  {cuts.map((cut,i)=> (
                    <div className="item" key={i} style={{marginBottom:12}}>
                      <div style={{fontWeight:600,marginBottom:4}}>컷 {cut.cut_id}: {cut.cut_name}</div>
                      <div className="help" style={{marginBottom:4}}>구도: {cut.composition}</div>
                      <div className="help" style={{marginBottom:4}}>배경: {cut.background}</div>
                      {cut.characters.length>0 && <div className="help" style={{marginBottom:4}}>인물: {cut.characters.join(', ')}</div>}
                      {cut.dialogues.length>0 && (
                        <div style={{marginTop:6}}>
                          <div className="help">대사:</div>
                          {cut.dialogues.map((d,j)=> (
                            <div key={j} style={{marginLeft:8,fontSize:12}}>• {d.speaker}: "{d.text}"</div>
                          ))}
                        </div>
                      )}
                      {cut.actions.length>0 && <div className="help" style={{marginTop:4}}>액션: {cut.actions.join(', ')}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {prompts.length>0 && (
              <div className="card project-card" style={{marginTop:12}}>
                <div className="section-title">이미지 생성 프롬프트 ({prompts.length}개)</div>
                <div className="list">
                  {prompts.map((p,i)=> <div className="item" key={i}>[{i+1}] {p}</div>)}
                </div>
                <div className="actions" style={{marginTop:8}}>
                  <button className="btn primary" onClick={generateImages} disabled={disabledImg}>{loading? '이미지 생성 중…':'이미지 생성'}</button>
                <button className="btn ghost" onClick={handleResetSaved}>초기화</button>
                </div>
              </div>
            )}

            {saved.length>0 && (
              <div className="card project-card" style={{marginTop:12}}>
                <div className="section-title">결과</div>
                <div className="list">
                  {saved.map((s,i)=> <div className="item" key={i}><a href={s} target="_blank" rel="noreferrer">{s}</a></div>)}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="card project-card">
            <div className="section-title">퓨전 모드</div>
            <div className="help">비디오 합성/블렌딩 기능은 추후 구현 예정입니다.</div>
            <div className="help" style={{marginTop:8}}>고양이와 용 같은 비디오를 합치는 기능이 여기에 추가됩니다.</div>
          </div>
        )}
      </div>

      <div className="sidebar">
        <div className="sidebar-inner">
          <h3>{projectMode === 'fusion' ? '퓨전 모드' : '스토리 모드'} 단계</h3>
          <div className="list">
            {projectMode === 'fusion' ? (
              <>
                <div className="item">1) 비디오 파일 업로드</div>
                <div className="item">2) 합성/블렌딩 설정</div>
                <div className="item">3) 결과 영상 생성(추후)</div>
              </>
            ) : (
              <>
                <div className="item">1) 각본 → 콘티 프롬프트</div>
                <div className="item">2) 이미지 생성</div>
                <div className="item">3) 대사/오디오 추가(추후)</div>
                <div className="item">4) 영상 합성(추후)</div>
              </>
            )}
          </div>
          
          {imageProgress.status && (
            <div style={{marginTop:16,padding:12,background:'rgba(255,255,255,.1)',borderRadius:8}}>
              <div style={{fontSize:12,marginBottom:8,color:'#cbd5e1'}}>{imageProgress.message || '진행 중...'}</div>
              <div style={{width:'100%',height:8,background:'rgba(0,0,0,.3)',borderRadius:4,overflow:'hidden'}}>
                <div style={{width:`${imageProgress.progress}%`,height:'100%',background:imageProgress.status==='error'?'#ef4444':imageProgress.status==='completed'?'#22c55e':'#2563eb',transition:'width 0.3s'}} />
              </div>
              <div style={{fontSize:11,marginTop:6,color:'#9ca3af'}}>{Math.round(imageProgress.progress)}%</div>
            </div>
          )}
          
          <div className="help" style={{marginTop:8}}>API: {API_BASE}</div>
        </div>
      </div>
    </div>
  )
}
