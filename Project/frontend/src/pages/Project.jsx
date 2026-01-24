import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE || ''
const normalizeSavedResults = (savedList, promptList = []) => {
  if(!Array.isArray(savedList)) return []
  return savedList.map((item, idx) => {
    if(typeof item === 'string'){
      return { index: idx, url: item, path: item, prompt: promptList[idx] || '' }
    }
    return {
      index: item?.index ?? idx,
      url: item?.url || item?.path || '',
      path: item?.path || '',
      prompt: item?.prompt ?? promptList[idx] ?? '',
      message: item?.message || ''
    }
  })
}

export default function Project(){
  const { id } = useParams()
  const nav = useNavigate()
  const stylePresets = useMemo(() => ([
    { key:'surreal', label:'초현실', img: '/iconImage/초현실.png' },
    { key:'real', label:'현실', img: '/iconImage/현실.png' },
    { key:'future', label:'미래', img: '/iconImage/미래.png' },
    { key:'simple3d', label:'심플3D', img: '/iconImage/심플3D.png' },
    { key:'ghibli', label:'지브리', img: '/iconImage/지브리.png' },
    { key:'dark', label:'다크 판타지', img: '/iconImage/다크판타지.png' },
  ]), [])
  const [styleCollapsed, setStyleCollapsed] = useState(true)
  const [selectedStyleKey, setSelectedStyleKey] = useState('surreal')
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
  const [lastSavedDraft, setLastSavedDraft] = useState({title:'', story:'', minShots:2, styleKey: 'surreal'})
  const [regenIndex, setRegenIndex] = useState(null)
  const [videoGenerating, setVideoGenerating] = useState(false)
  const [videoPath, setVideoPath] = useState('')
  const [ttsType, setTtsType] = useState('google')  // 'google' 또는 'gemini'
  const [ttsStyle, setTtsStyle] = useState('유튜버')  // '유튜버', '나레이션', '캐릭터'
  const [ttsCollapsed, setTtsCollapsed] = useState(true)
  const selectedStyle = useMemo(() => stylePresets.find(s => s.key === selectedStyleKey) || stylePresets[0], [stylePresets, selectedStyleKey])
  
  const ttsPresets = useMemo(() => ([
    { 
      key: 'google', 
      label: 'Google TTS', 
      description: '안정적인 Google Neural2 음성',
      features: ['SSML 지원', '안정적', '다양한 음성']
    },
    { 
      key: 'gemini', 
      label: 'Gemini AI TTS', 
      description: 'AI 감정 표현, 유튜버 스타일',
      features: ['감정 태그', 'GPT 대사 강화', '유튜버 스타일']
    }
  ]), [])
  
  const ttsStylePresets = useMemo(() => ([
    { key: '유튜버', label: '유튜버', description: '하이텐션, 신나는 스타일' },
    { key: '나레이션', label: '나레이션', description: '차분하고 전문적인 스타일' },
    { key: '캐릭터', label: '캐릭터', description: '개성있는 캐릭터 연기' }
  ]), [])

  // 백엔드에서 온 상대 경로(/media/...)를 절대 URL로 변환
  const resolveMediaUrl = useCallback((value) => {
    if(!value) return ''
    if(typeof value !== 'string') return ''
    if(value.startsWith('http://') || value.startsWith('https://')) return value
    if(value.startsWith('/')) return `${API_BASE}${value}`
    return value
  }, [])

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
        if(data.state?.style_key){
          setSelectedStyleKey(data.state.style_key)
        }
        setTitle(state.title ?? data.meta?.title ?? '')
        setStory(state.story ?? '')
        setMinShots(state.min_shots_per_scene ?? 2)
        const loadedPrompts = state.prompts ?? []
        setPrompts(loadedPrompts)
        setCuts(state.cuts ?? [])
        setSaved(normalizeSavedResults(state.saved_results ?? [], loadedPrompts))
        setImageProgress(state.image_progress ?? {status:'',progress:0,message:''})
        setImageJobId(state.image_job_id ?? '')
        setVideoPath(state.video_path || '')
        setLastSavedDraft({
          title: state.title ?? data.meta?.title ?? '',
          story: state.story ?? '',
          minShots: state.min_shots_per_scene ?? 2,
          styleKey: state.style_key ?? 'surreal'
        })
        setError('')
        setProjectLoaded(true)
        setLoading(Boolean(state.image_job_id))
      }catch(e){
        if(!active) return
        setError(e?.message || '프로젝트 정보를 불러올 수 없습니다')
        setProjectLoaded(true) // 에러 발생 시에도 로드 완료로 표시하여 UI 렌더링
      }
    }
    loadProject()
    return () => { active = false }
  }, [id])

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
          minShots: data.state.min_shots_per_scene ?? 1,
          styleKey: data.state.style_key ?? 'surreal'
        })
      }
    }catch(e){
      console.warn('프로젝트 상태 저장 실패', e)
    }
  }, [projectLoaded, id])

  useEffect(() => {
    if(!projectLoaded) return
    if(lastSavedDraft.styleKey === selectedStyleKey) return
    saveProjectState({ style_key: selectedStyleKey })
    // 스타일 변경 시 기존 프롬프트가 있으면 재생성
    if(cuts.length > 0 && story.trim()) {
      // 사용자에게 알림만 표시 (자동 재생성은 하지 않음)
      // 필요시 createStoryboard()를 호출하여 재생성 가능
    }
  }, [selectedStyleKey, projectLoaded, lastSavedDraft.styleKey, saveProjectState, cuts.length, story])

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
          setSaved(normalizeSavedResults(prog.results||[], prompts))
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
      const res = await fetch(`${API_BASE}/api/storyboard`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_id: id, story, title: title || undefined, min_shots_per_scene: Number(minShots)||1, style_key: selectedStyleKey })})
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
    setSaved([])
    try{
      const res = await fetch(`${API_BASE}/api/images`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_id: id, prompts, output_dir: 'Project/data/outputs', model: 'fal-ai/flux/dev', size: 'portrait_16_9' })})
      if(!res.ok) throw new Error(`Images failed (${res.status})`)
      const data = await res.json()
      setImageJobId(data.job_id)
    }catch(e){ setError(e?.message || '오류가 발생했습니다'); setLoading(false); setImageProgress({status:'',progress:0,message:''}) }
  }

  const handleSavedPromptChange = (idx, value) => {
    setSaved(prev => prev.map((item, i) => i === idx ? {...item, prompt: value} : item))
    setPrompts(prev => {
      const next = [...prev]
      next[idx] = value
      return next
    })
  }

  const regenerateImage = async (idx) => {
    const target = saved[idx] || {}
    const promptText = target.prompt || prompts[idx] || ''
    if(!promptText){
      setError('프롬프트가 비어 있습니다')
      return
    }
    setRegenIndex(idx); setError('')
    try{
      const res = await fetch(`${API_BASE}/api/images/regenerate`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ project_id: id, index: idx, prompt: promptText, model:'fal-ai/flux/dev', size:'portrait_16_9', output_dir:'Project/data/outputs' })
      })
      if(!res.ok) throw new Error('재생성 실패')
      const data = await res.json()
      const updated = normalizeSavedResults([data.result], [promptText])[0]
      const nextSaved = [...saved]
      nextSaved[idx] = updated
      setSaved(nextSaved)
      const nextPrompts = [...prompts]
      nextPrompts[idx] = promptText
      setPrompts(nextPrompts)
      await saveProjectState({ prompts: nextPrompts, saved_results: nextSaved })
    }catch(e){
      setError(e?.message || '재생성 중 오류가 발생했습니다')
    }finally{
      setRegenIndex(null)
    }
  }

  const handleResetSaved = async () => {
    setSaved([])
    setVideoPath('')
    await saveProjectState({ saved_results: [], video_path: '' })
  }

  const generateVideo = async () => {
    if(saved.length === 0){
      setError('생성된 이미지가 없습니다. 먼저 이미지를 생성해주세요.')
      return
    }
    
    // 모든 이미지 경로 추출
    const imagePaths = saved
      .map(s => s.path || s.url)
      .filter(path => path && path.trim())
    
    if(imagePaths.length === 0){
      setError('유효한 이미지 경로가 없습니다.')
      return
    }
    
    setVideoGenerating(true)
    setError('')
    
    try{
      const res = await fetch(`${API_BASE}/api/video`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: id,
          image_paths: imagePaths,
          fps: 24,
          tts_type: ttsType,
          tts_style: ttsStyle
        })
      })
      
      if(!res.ok){
        const errorData = await res.json().catch(() => ({detail: `Video generation failed (${res.status})`}))
        throw new Error(errorData.detail || `Video generation failed (${res.status})`)
      }
      
      const data = await res.json()
      setVideoPath(data.output || data.metadata?.output_path || '')
      
      // 프로젝트 상태 업데이트
      await saveProjectState({
        video_path: data.output || data.metadata?.output_path || '',
        video_clips: data.metadata?.clip_paths || [],
        audio_paths: data.metadata?.audio_paths || [],
        video_duration: data.metadata?.total_duration || 0
      })
      
    }catch(e){
      setError(e?.message || '영상 생성 중 오류가 발생했습니다')
    }finally{
      setVideoGenerating(false)
    }
  }

  const deleteProject = async () => {
    if(!confirm('정말 이 프로젝트를 삭제하시겠습니까?')) return
    try{
      const res = await fetch(`${API_BASE}/api/projects/${id}`, {method:'DELETE'})
      if(!res.ok) throw new Error('삭제 실패')
      nav('/')
    }catch(e){ setError(e?.message || '삭제 중 오류가 발생했습니다') }
  }

  if (!projectLoaded) {
    return (
      <div className="shell" style={{paddingTop:24, display:'flex', alignItems:'center', justifyContent:'center', minHeight:'50vh'}}>
        <div style={{textAlign:'center'}}>
          <div className="section-title">프로젝트 로딩 중...</div>
          <div className="help">프로젝트 정보를 불러오는 중입니다.</div>
        </div>
      </div>
    )
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

        {error && (
          <div className="card project-card" style={{marginBottom:12, background:'#fef2f2', borderColor:'#ef4444'}}>
            <div className="section-title" style={{color:'#ef4444'}}>⚠ 오류 발생</div>
            <div className="help" style={{color:'#dc2626'}}>{error}</div>
          </div>
        )}

        {/* 스타일 선택 (접힘/펼침) */}
        <div className="card project-card" style={{marginBottom:12}}>
          <div className="style-header" onClick={()=>setStyleCollapsed(!styleCollapsed)}>
            <div style={{display:'flex',alignItems:'center',gap:10}}>
              <div className={`chevron ${styleCollapsed?'collapsed':''}`}>▾</div>
              <div style={{fontWeight:700}}>이미지 스타일 선택</div>
            </div>
            <div className="style-selected">
              <span className="help" style={{marginRight:6}}>현재 스타일</span>
              <img src={selectedStyle.img} alt={selectedStyle.label} className="style-thumb" />
              <span style={{fontWeight:600}}>{selectedStyle.label}</span>
            </div>
          </div>
          {!styleCollapsed && (
            <div className="style-grid">
              {stylePresets.map(p => (
                <button
                  key={p.key}
                  className={`style-tile ${selectedStyleKey===p.key?'active':''}`}
                  onClick={()=>setSelectedStyleKey(p.key)}
                >
                  <img src={p.img} alt={p.label} className="style-thumb-lg" />
                  <div className="style-label">{p.label}</div>
                </button>
              ))}
            </div>
          )}
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
                <div className="section-title">
                  컷별 요소 ({cuts.length}개)
                  <span style={{marginLeft:8,fontSize:12,fontWeight:400,color:'#22c55e'}}>
                    ✓ 나레이션: {cuts.filter(c => c.dialogues?.some(d => d.speaker?.includes('나레이션'))).length}/{cuts.length}
                  </span>
                </div>
                <div className="list">
                  {cuts.map((cut,i)=> {
                    const hasNarration = cut.dialogues?.some(d => d.speaker?.includes('나레이션'))
                    return (
                      <div className="item" key={i} style={{marginBottom:12,borderLeft:hasNarration?'3px solid #22c55e':'3px solid #ef4444',paddingLeft:12}}>
                        <div style={{fontWeight:600,marginBottom:4}}>
                          컷 {cut.cut_id}: {cut.cut_name}
                          {!hasNarration && <span style={{marginLeft:8,fontSize:11,color:'#ef4444'}}>⚠ 나레이션 없음</span>}
                        </div>
                        <div className="help" style={{marginBottom:4}}>구도: {cut.composition}</div>
                        <div className="help" style={{marginBottom:4}}>배경: {cut.background}</div>
                        {cut.characters.length>0 && <div className="help" style={{marginBottom:4}}>인물: {cut.characters.join(', ')}</div>}
                        {cut.dialogues.length>0 && (
                          <div style={{marginTop:6}}>
                            <div className="help">대사/나레이션:</div>
                            {cut.dialogues.map((d,j)=> {
                              const isNarration = d.speaker?.includes('나레이션')
                              return (
                                <div key={j} style={{
                                  marginLeft:8,
                                  fontSize:12,
                                  background: isNarration ? '#f0fdf4' : 'transparent',
                                  padding: isNarration ? '4px 8px' : '0',
                                  borderRadius: isNarration ? '4px' : '0',
                                  marginBottom:4
                                }}>
                                  • <strong style={{color: isNarration ? '#22c55e' : '#2563eb'}}>{d.speaker}</strong>: "{d.text}"
                                </div>
                              )
                            })}
                          </div>
                        )}
                        {cut.actions.length>0 && <div className="help" style={{marginTop:4}}>액션: {cut.actions.join(', ')}</div>}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {prompts.length>0 && (
              <div className="card project-card" style={{marginTop:12}}>
                <div className="section-title">이미지 생성 프롬프트 ({prompts.length}개)</div>
                <div className="help" style={{marginBottom:8,color:'#2563eb'}}>💡 스타일을 변경한 경우, 프롬프트를 새로 생성하려면 "스토리보드 생성" 버튼을 다시 클릭하세요.</div>
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
              <>
                <div className="card project-card" style={{marginTop:12}}>
                  <div className="section-title">생성된 이미지 미리보기</div>
                  <div className="help" style={{marginBottom:8}}>각 이미지 아래 프롬프트를 수정하고 해당 컷만 다시 생성할 수 있습니다.</div>
                  <div className="image-grid">
                    {saved.map((s,i)=> (
                      <div className="image-card" key={i}>
                        <div className="image-preview">
                          {(s.url || s.path) ? (
                            <img 
                              src={resolveMediaUrl(s.url || s.path)} 
                              alt={`컷 ${i+1}`} 
                              style={{width:'100%',height:'100%',objectFit:'cover',borderRadius:12}} 
                            />
                          ) : (
                            <div className="help" style={{textAlign:'center'}}>이미지가 없습니다</div>
                          )}
                        </div>
                        <div className="help" style={{margin:'8px 0 4px'}}>프롬프트</div>
                        <textarea className="input" style={{minHeight:90}} value={s.prompt || prompts[i] || ''} onChange={e=>handleSavedPromptChange(i, e.target.value)} />
                        <div className="image-actions">
                          <button className="btn primary" onClick={()=>regenerateImage(i)} disabled={regenIndex===i || loading}>{regenIndex===i ? '재생성 중…' : '이 프롬프트로 다시 생성'}</button>
                          {(s.url || s.path) && (
                            <a 
                              className="btn ghost" 
                              href={resolveMediaUrl(s.url || s.path)} 
                              target="_blank" 
                              rel="noreferrer" 
                              style={{textAlign:'center',display:'inline-block',padding:'10px 14px'}}
                            >
                              원본 열기
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="card project-card" style={{marginTop:12}}>
                  <div className="section-title">영상 생성</div>
                  <div className="help" style={{marginBottom:8}}>생성된 이미지들로 자막과 TTS가 포함된 영상을 만듭니다.</div>
                  
                  {/* TTS 선택 옵션 */}
                  <div style={{marginBottom:16, padding:12, background:'rgba(0,0,0,0.03)', borderRadius:8}}>
                    <div 
                      className="style-header" 
                      onClick={()=>setTtsCollapsed(!ttsCollapsed)}
                      style={{cursor:'pointer', marginBottom: ttsCollapsed ? 0 : 12}}
                    >
                      <div style={{display:'flex',alignItems:'center',gap:10}}>
                        <div className={`chevron ${ttsCollapsed?'collapsed':''}`}>▾</div>
                        <div style={{fontWeight:700}}>🔊 TTS 음성 설정</div>
                      </div>
                      <div style={{display:'flex', alignItems:'center', gap:8}}>
                        <span className="help">현재:</span>
                        <span style={{fontWeight:600, color: ttsType === 'gemini' ? '#8b5cf6' : '#2563eb'}}>
                          {ttsType === 'gemini' ? 'Gemini AI' : 'Google TTS'}
                        </span>
                        {ttsType === 'gemini' && (
                          <span style={{fontSize:11, color:'#6b7280'}}>({ttsStyle})</span>
                        )}
                      </div>
                    </div>
                    
                    {!ttsCollapsed && (
                      <div style={{display:'flex', flexDirection:'column', gap:12}}>
                        {/* TTS 타입 선택 */}
                        <div>
                          <div className="help" style={{marginBottom:6}}>TTS 엔진 선택</div>
                          <div style={{display:'flex', gap:8}}>
                            {ttsPresets.map(preset => (
                              <button
                                key={preset.key}
                                className={`btn ${ttsType === preset.key ? 'primary' : 'ghost'}`}
                                onClick={() => setTtsType(preset.key)}
                                style={{
                                  flex:1, 
                                  padding:'12px 16px', 
                                  textAlign:'left',
                                  border: ttsType === preset.key ? 'none' : '1px solid #e5e7eb'
                                }}
                              >
                                <div style={{fontWeight:600, marginBottom:4}}>
                                  {preset.key === 'gemini' ? '✨ ' : '🔊 '}{preset.label}
                                </div>
                                <div style={{fontSize:11, opacity:0.8}}>{preset.description}</div>
                              </button>
                            ))}
                          </div>
                        </div>
                        
                        {/* Gemini 스타일 선택 (Gemini 선택 시에만 표시) */}
                        {ttsType === 'gemini' && (
                          <div>
                            <div className="help" style={{marginBottom:6}}>AI 음성 스타일</div>
                            <div style={{display:'flex', gap:8}}>
                              {ttsStylePresets.map(preset => (
                                <button
                                  key={preset.key}
                                  className={`btn ${ttsStyle === preset.key ? 'primary' : 'ghost'}`}
                                  onClick={() => setTtsStyle(preset.key)}
                                  style={{
                                    flex:1,
                                    padding:'10px 12px',
                                    textAlign:'center',
                                    border: ttsStyle === preset.key ? 'none' : '1px solid #e5e7eb'
                                  }}
                                >
                                  <div style={{fontWeight:600}}>{preset.label}</div>
                                  <div style={{fontSize:10, opacity:0.7}}>{preset.description}</div>
                                </button>
                              ))}
                            </div>
                            <div className="help" style={{marginTop:8, padding:8, background:'rgba(139,92,246,0.1)', borderRadius:4, color:'#7c3aed'}}>
                              💡 Gemini AI TTS는 GPT로 대사를 자동 강화하여 감정과 억양을 자연스럽게 표현합니다.
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <div className="actions" style={{display:'flex', gap:8, alignItems:'center'}}>
                    <button 
                      className="btn primary" 
                      onClick={generateVideo} 
                      disabled={videoGenerating || saved.length === 0 || saved.some(s => !s.path && !s.url)}
                    >
                      {videoGenerating ? '영상 생성 중…' : `영상 생성 (${ttsType === 'gemini' ? 'Gemini AI' : 'Google'} TTS)`}
                    </button>
                  </div>
                  {videoGenerating && (
                    <div className="help" style={{marginTop:8,color:'#2563eb'}}>
                      영상을 생성하는 중입니다. TTS 생성과 영상 합성에 시간이 걸릴 수 있습니다...
                    </div>
                  )}
                  {videoPath && (
                    <div style={{marginTop:12}}>
                      <div className="help" style={{marginBottom:4}}>✅ 영상 생성 완료 · 아래 플레이 버튼을 눌러 바로 재생할 수 있습니다.</div>
                      <video 
                        src={resolveMediaUrl(videoPath)} 
                        controls 
                        style={{width:'100%',maxHeight:480,borderRadius:12,background:'black'}}
                      />
                    </div>
                  )}
                </div>
              </>
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
          {/* 영상이 생성되었을 때 쇼츠 스타일 플레이어 표시 */}
          {videoPath ? (
            <div className="shorts-player">
              <h3 style={{marginBottom:12}}>🎬 생성된 영상</h3>
              <div className="shorts-container">
                <video 
                  src={resolveMediaUrl(videoPath)} 
                  controls 
                  autoPlay
                  loop
                  playsInline
                  className="shorts-video"
                />
                <div className="shorts-overlay">
                  <div className="shorts-title">{title || '무제'}</div>
                  <div className="shorts-info">
                    총 {cuts.length}개 컷 · {saved.length}개 이미지
                  </div>
                </div>
              </div>
              <div style={{marginTop:12,display:'flex',gap:8,flexDirection:'column'}}>
                <a 
                  className="btn primary" 
                  href={resolveMediaUrl(videoPath)} 
                  download 
                  style={{textAlign:'center',textDecoration:'none',width:'100%'}}
                >
                  ⬇ 다운로드
                </a>
                <button 
                  className="btn ghost" 
                  onClick={() => {
                    const videoEl = document.querySelector('.shorts-video')
                    if (videoEl) {
                      if (videoEl.paused) videoEl.play()
                      else videoEl.pause()
                    }
                  }}
                  style={{width:'100%'}}
                >
                  ⏯ 재생/일시정지
                </button>
              </div>
            </div>
          ) : (
            <>
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
                    <div className="item">3) 대사/오디오 추가</div>
                    <div className="item">4) 영상 합성</div>
                  </>
                )}
              </div>
            </>
          )}
          
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
