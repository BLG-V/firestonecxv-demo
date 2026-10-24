import { useEffect, useMemo, useRef, useState } from 'react'
import { api, clearVerificationToken, getVerificationToken, saveVerificationToken } from './api'
import type { AIAnalysisResult, ChainHealth, ChainPosition, ChainProfile, EnterpriseSummary, GapAnalysis, SegmentEnterprise } from './types'

type View = 'enterprise' | 'chain'
type Tone = 'neutral' | 'good' | 'warn' | 'bad'

const defaultChainId = import.meta.env.VITE_CHAIN_ID || 'nev'
const dimensionNames: Record<string, string> = {
  strategic: '战略价值',
  value_added: '增加值',
  scarcity: '稀缺程度',
  growth: '成长空间',
}

function enterpriseId(item: EnterpriseSummary): string {
  return item.enterprise_id || item.id || ''
}

function enterpriseName(item: EnterpriseSummary): string {
  return item.enterprise_name || item.name || enterpriseId(item)
}

function number(value: number | null | undefined, digits = 1): string {
  return value == null || !Number.isFinite(value) ? '暂未获取' : value.toFixed(digits)
}

function text(value: string | null | undefined): string {
  return value?.trim() || '暂未获取'
}

function potential(position: ChainPosition): boolean {
  return /potential|潜在/i.test(position.match_level + ' ' + position.status)
}

function positionKind(position: ChainPosition): string {
  if (potential(position)) return '潜在方向 · 待核验'
  if (/primary|main|主营/i.test(position.match_level)) return '主营环节'
  if (/secondary|次要/i.test(position.match_level)) return '次要环节'
  return '现有环节'
}

function positionStatus(position: ChainPosition): { label: string; tone: Tone } {
  if (/rejected|reject|驳回|否决/i.test(position.status)) return { label: '已驳回', tone: 'bad' }
  if (/confirmed|confirm|已核验/i.test(position.status)) return { label: '已核验', tone: 'good' }
  return { label: '待核验', tone: 'warn' }
}

function decisionState(profile: ChainProfile): { label: string; tone: Tone } {
  if (profile.where.abstained) return { label: '定位弃权', tone: 'warn' }
  if (profile.data_stale) return { label: '数据过期', tone: 'warn' }
  const state = profile.decision_status || profile.decision?.decision_status
  if (state === 'vetoed' || (profile.decision?.vetoes?.length || 0) > 0) return { label: '触发否决', tone: 'bad' }
  if (state === 'data_pending' || !profile.decision) return { label: '待补数据', tone: 'warn' }
  return { label: '可研判', tone: 'good' }
}

function aiDecisionLabel(status: string): string {
  const labels: Record<string, string> = {
    scored: '规则研判：可评分',
    vetoed: '规则研判：触发否决',
    data_pending: '规则研判：待补数据',
    abstained: '规则研判：定位弃权',
    stale: '规则研判：数据过期',
  }
  return labels[status] || '规则状态：' + status
}

function healthLabel(status?: string): string {
  if (!status) return '待核验'
  const labels: Record<string, string> = {
    strong: '基础较强', healthy: '基础较强', weak: '基础薄弱', broken: '链条断点', gap: '关键缺口', missing: '关键缺口',
  }
  return labels[status] || status
}

function gapLevel(level?: string): string {
  const labels: Record<string, string> = { critical: '严重缺口', high: '较大缺口', mid: '中度缺口', low: '轻度缺口', none: '无明显缺口' }
  return level ? labels[level] || level : '暂未获取'
}

function gapText(item: string | { missing_field?: string; impact?: string }): string {
  if (typeof item === 'string') return item
  return [item.missing_field, item.impact].filter(Boolean).join('：') || '暂未获取'
}

function Pill({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: Tone }) {
  return <span className={'pill pill-' + tone}>{children}</span>
}

function Empty({ title, detail }: { title: string; detail?: string }) {
  return <div className="empty"><span className="empty-mark">—</span><strong>{title}</strong>{detail && <p>{detail}</p>}</div>
}

function SectionHeading({ index, eyebrow, title, note }: { index: string; eyebrow: string; title: string; note?: string }) {
  return <div className="section-heading"><span className="section-index">{index}</span><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2>{note && <p>{note}</p>}</div></div>
}

export default function App() {
  const [view, setView] = useState<View>('enterprise')
  const [query, setQuery] = useState('')
  const [enterprises, setEnterprises] = useState<EnterpriseSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [profile, setProfile] = useState<ChainProfile | null>(null)
  const [chain, setChain] = useState<ChainHealth | null>(null)
  const [selectedSegment, setSelectedSegment] = useState('')
  const [segmentEnterprises, setSegmentEnterprises] = useState<SegmentEnterprise[]>([])
  const [gap, setGap] = useState<GapAnalysis | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [loadingChain, setLoadingChain] = useState(false)
  const [loadingSegment, setLoadingSegment] = useState(false)
  const [listError, setListError] = useState('')
  const [profileError, setProfileError] = useState('')
  const [chainError, setChainError] = useState('')
  const [segmentError, setSegmentError] = useState('')
  const [notice, setNotice] = useState('')
  const [verifyBusy, setVerifyBusy] = useState<number | null>(null)
  const [correctingId, setCorrectingId] = useState<number | null>(null)
  const [correctedSegment, setCorrectedSegment] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [aiAnalysis, setAiAnalysis] = useState<{ enterpriseId: string; result: AIAnalysisResult } | null>(null)
  const [aiError, setAiError] = useState<{ enterpriseId: string; message: string } | null>(null)
  const [aiLoadingFor, setAiLoadingFor] = useState('')
  const aiRequestSequence = useRef(0)
  const aiInFlightFor = useRef('')
  const [verificationTokenDraft, setVerificationTokenDraft] = useState(() => getVerificationToken())
  const [verificationTokenConfigured, setVerificationTokenConfigured] = useState(() => Boolean(getVerificationToken()))

  const filteredEnterprises = useMemo(() => enterprises.filter(item =>
    enterpriseName(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()) ||
    (item.industry || '').toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  ), [enterprises, query])

  const chainId = profile?.where.positions.find(item => item.chain_id)?.chain_id || defaultChainId
  const currentEnterprise = enterprises.find(item => enterpriseId(item) === selectedId)
  const currentSegment = chain?.segments.find(item => item.segment_id === selectedSegment)
  const positionCount = profile?.where.positions.length || 0
  const state = profile ? decisionState(profile) : null
  const evidenceRows = profile ? [
    ...profile.where.positions.flatMap(position => (position.evidence || []).map((evidence, index) => ({
      evidence,
      label: position.segment_name,
      key: (position.position_id || position.id || position.segment_id) + '-position-' + index,
    }))),
    ...(profile.explanation?.drivers || []).flatMap((driver, driverIndex) => (driver.evidence || []).map((evidence, index) => ({
      evidence,
      label: driver.factor_name || '演示规则因子',
      key: 'driver-' + driverIndex + '-' + index,
    }))),
  ] : []

  useEffect(() => {
    let active = true
    api.enterprises().then(items => {
      if (!active) return
      const list = Array.isArray(items) ? items : []
      setEnterprises(list)
      setSelectedId(previous => previous || (list[0] ? enterpriseId(list[0]) : ''))
      setListError('')
    }).catch(error => active && setListError(error instanceof Error ? error.message : '企业列表加载失败'))
      .finally(() => active && setLoadingList(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!selectedId) return
    let active = true
    setLoadingProfile(true)
    setProfileError('')
    api.profile(selectedId).then(result => {
      if (active) setProfile(result)
    }).catch(error => {
      if (active) { setProfile(null); setProfileError(error instanceof Error ? error.message : '画像加载失败') }
    }).finally(() => active && setLoadingProfile(false))
    return () => { active = false }
  }, [selectedId, refresh])

  useEffect(() => {
    aiRequestSequence.current += 1
    aiInFlightFor.current = ''
    setAiAnalysis(null)
    setAiError(null)
    setAiLoadingFor('')
  }, [selectedId, refresh])

  useEffect(() => {
    let active = true
    setLoadingChain(true)
    setChainError('')
    api.chainHealth(chainId).then(result => {
      if (!active) return
      setChain(result)
      setSelectedSegment(previous => result.segments.some(item => item.segment_id === previous) ? previous : result.segments[0]?.segment_id || '')
    }).catch(error => {
      if (active) { setChain(null); setChainError(error instanceof Error ? error.message : '图谱加载失败') }
    }).finally(() => active && setLoadingChain(false))
    return () => { active = false }
  }, [chainId, refresh])

  useEffect(() => {
    if (!selectedSegment) return
    let active = true
    setLoadingSegment(true)
    setSegmentError('')
    Promise.all([api.segmentEnterprises(selectedSegment), api.gapAnalysis(selectedSegment)]).then(([items, analysis]) => {
      if (!active) return
      setSegmentEnterprises(Array.isArray(items) ? items : [])
      setGap(analysis)
    }).catch(error => {
      if (active) { setGap(null); setSegmentEnterprises([]); setSegmentError(error instanceof Error ? error.message : '环节详情加载失败') }
    }).finally(() => active && setLoadingSegment(false))
    return () => { active = false }
  }, [selectedSegment, refresh])

  async function verify(position: ChainPosition, action: 'confirm' | 'reject' | 'correct') {
    const id = position.position_id || position.id
    if (!id || (action === 'correct' && !correctedSegment)) return
    setVerifyBusy(id)
    setNotice('')
    try {
      await api.verify(id, action, action === 'correct' ? correctedSegment : undefined)
      setNotice(action === 'confirm' ? '核验已确认，画像已刷新。' : action === 'reject' ? '定位已驳回，画像已刷新。' : '环节已纠正，画像已刷新。')
      setCorrectingId(null)
      setCorrectedSegment('')
      setRefresh(value => value + 1)
    } catch (error) {
      setNotice(error instanceof Error ? '核验失败：' + error.message : '核验失败，请重试')
    } finally {
      setVerifyBusy(null)
    }
  }

  async function runAiAnalysis() {
    if (!selectedId || aiInFlightFor.current === selectedId) return
    const enterpriseId = selectedId
    const requestSequence = ++aiRequestSequence.current
    aiInFlightFor.current = enterpriseId
    setAiAnalysis(null)
    setAiError(null)
    setAiLoadingFor(enterpriseId)
    try {
      const result = await api.aiAnalysis(enterpriseId)
      if (aiRequestSequence.current === requestSequence) setAiAnalysis({ enterpriseId, result })
    } catch (error) {
      if (aiRequestSequence.current === requestSequence) {
        setAiError({ enterpriseId, message: error instanceof Error ? error.message : 'AI 分析失败，请重试' })
      }
    } finally {
      if (aiRequestSequence.current === requestSequence) {
        aiInFlightFor.current = ''
        setAiLoadingFor('')
      }
    }
  }

  function saveVerificationTokenDraft() {
    const token = verificationTokenDraft.trim()
    if (!token) return
    saveVerificationToken(token)
    setVerificationTokenDraft(token)
    setVerificationTokenConfigured(true)
  }

  function clearVerificationTokenDraft() {
    clearVerificationToken()
    setVerificationTokenDraft('')
    setVerificationTokenConfigured(false)
  }

  function openEnterprise(id: string) {
    aiRequestSequence.current += 1
    aiInFlightFor.current = ''
    setAiAnalysis(null)
    setAiError(null)
    setAiLoadingFor('')
    setSelectedId(id)
    setProfile(null)
    setNotice('')
    setView('enterprise')
  }

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-glyph" aria-hidden="true"><i /><i /><i /></div><div><strong>链脉</strong><span>CHAIN INTELLIGENCE</span></div></div>
      <div className="workspace-label">研判工作台 <span>DEMO / 01</span></div>
      <nav className="primary-nav" aria-label="主导航">
        <button type="button" className={view === 'enterprise' ? 'nav-item active' : 'nav-item'} onClick={() => setView('enterprise')}><span className="nav-icon">◈</span> 企业画像 <span className="nav-arrow">↗</span></button>
        <button type="button" className={view === 'chain' ? 'nav-item active' : 'nav-item'} onClick={() => setView('chain')}><span className="nav-icon">⬡</span> 产业链图谱 <span className="nav-arrow">↗</span></button>
      </nav>
      <div className="sidebar-rule" />
      <div className="list-heading"><span>企业清单</span><span className="list-count">{enterprises.length.toString().padStart(2, '0')}</span></div>
      <label className="search-box"><span aria-hidden="true">⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索企业或行业" aria-label="搜索企业或行业" /></label>
      <div className="enterprise-list">
        {loadingList && <p className="sidebar-note">正在加载企业…</p>}
        {listError && <p className="sidebar-note error">{listError}</p>}
        {!loadingList && !listError && filteredEnterprises.length === 0 && <p className="sidebar-note">没有匹配的企业</p>}
        {filteredEnterprises.map((item, index) => <button key={enterpriseId(item) || index} type="button" className={selectedId === enterpriseId(item) ? 'enterprise-item selected' : 'enterprise-item'} onClick={() => openEnterprise(enterpriseId(item))}>
          <span className="enterprise-monogram">{enterpriseName(item).slice(0, 1)}</span><span className="enterprise-item-copy"><strong>{enterpriseName(item)}</strong><small>{item.primary_segment_name || item.home_region || item.industry || item.region || '演示企业'}</small></span><span className="enterprise-chevron">›</span>
        </button>)}
      </div>
      <div className="sidebar-bottom"><span className="live-dot" /> 演示环境 · 模拟数据<br /><small>所有分数均为未校准规则匹配分</small></div>
    </aside>

    <div className="main-area">
      <header className="topbar"><div className="breadcrumbs">产业研究 <span>/</span> {view === 'enterprise' ? '企业画像' : '产业链图谱'}</div><div className="topbar-right"><span className="topbar-date">数据模式 / SYNTHETIC</span><details className="token-control"><summary aria-label="设置人工核验令牌">{verificationTokenConfigured ? '核验令牌已配置' : '人工核验令牌'}</summary><div className="token-popover"><label htmlFor="verification-token">人工核验令牌<input id="verification-token" type="password" autoComplete="new-password" spellCheck={false} value={verificationTokenDraft} onChange={event => setVerificationTokenDraft(event.target.value)} placeholder="输入人工核验令牌" /></label><div className="token-actions"><button type="button" className="button accent" disabled={!verificationTokenDraft.trim()} onClick={saveVerificationTokenDraft}>保存</button><button type="button" className="button quiet" disabled={!verificationTokenConfigured && !verificationTokenDraft} onClick={clearVerificationTokenDraft}>清除</button></div><small>仅存于当前标签页会话；AI 分析公开且不使用此令牌。</small></div></details><Pill tone="warn">仅供演示</Pill></div></header>
      <main className="content">
        {view === 'enterprise' ? <>
          <div className="page-intro"><div><div className="eyebrow">ENTERPRISE INTELLIGENCE / 01</div><h1>{profile?.enterprise_name || (currentEnterprise && enterpriseName(currentEnterprise)) || '企业画像'}</h1><p>从产业链定位到招商判断，沿证据链逐层查看。</p></div>{profile && <div className="intro-meta"><Pill tone={state?.tone}>{state?.label}</Pill><span>数据截至 {text(profile.data_as_of)}</span></div>}</div>
          {notice && <div className="notice" role="status">{notice}<button type="button" onClick={() => setNotice('')} aria-label="关闭提示">×</button></div>}
          {loadingProfile && <div className="loading-block">正在形成企业画像 <span className="loading-dots">···</span></div>}
          {profileError && <div className="error-block"><strong>画像暂时无法加载</strong><p>{profileError}</p><button type="button" className="button quiet" onClick={() => setRefresh(value => value + 1)}>重试</button></div>}
          {!loadingProfile && !profileError && !profile && <Empty title="请从左侧选择企业" detail="选择演示企业后即可查看产业链融合画像。" />}
          {profile && !loadingProfile && <>
            <div className="snapshot-bar"><span><b>01</b> 定位环节 <strong>{profile.where.abstained ? '待核实' : positionCount}</strong></span><span><b>02</b> 环节价值 <strong>{profile.worth?.icv_score == null ? '待补数据' : number(profile.worth.icv_score)}</strong></span><span><b>03</b> 招商判断 <strong>{state?.label}</strong></span><span><b>04</b> 证据追溯 <strong>{profile.where.positions.reduce((sum, item) => sum + (item.evidence?.length || 0), 0)} 条</strong></span></div>

            <section className="section where-section"><SectionHeading index="01" eyebrow="WHERE IT FITS" title="在哪" note="基于产品、客户与经营事实定位；潜在方向单独标记。" />
              {profile.where.abstained ? <div className="abstain-panel"><span className="abstain-symbol">?</span><div><strong>证据不足，暂不定位</strong><p>{text(profile.where.abstain_reason)}</p>{(profile.where.missing_signals || []).length > 0 && <div className="inline-list">待补信号：{profile.where.missing_signals?.join('、')}</div>}</div></div> : positionCount === 0 ? <Empty title="暂未获取环节定位" /> : <div className="positions">
                {profile.where.positions.map((position, index) => <article className={'position-card ' + (potential(position) ? 'potential' : '')} key={position.position_id || position.id || index}>
                  <div className="position-rail"><span className="rail-point" /><span className="rail-line" /></div>
                  <div className="position-body"><div className="position-top"><div><div className="position-chain">{position.chain_name}</div><h3>{position.segment_name}</h3></div><Pill tone={potential(position) ? 'warn' : positionStatus(position).tone}>{positionKind(position)}</Pill></div>
                    <div className="position-detail"><span>匹配分 <strong>{number(position.match_score, 2)}</strong> <small>{position.score_kind?.startsWith('manual') ? '人工核验指示值' : '未校准规则分'}</small></span><span>状态 <strong>{positionStatus(position).label}</strong></span><span>证据 <strong>{position.evidence?.length || 0} 条</strong></span></div>
                    <div className="position-actions"><button type="button" className="button accent" disabled={verifyBusy === (position.position_id || position.id) || !position.position_id && !position.id} onClick={() => verify(position, 'confirm')}>确认定位</button><button type="button" className="button quiet" disabled={verifyBusy === (position.position_id || position.id) || !position.position_id && !position.id} onClick={() => verify(position, 'reject')}>驳回</button><button type="button" className="button text-button" onClick={() => { setCorrectingId(position.position_id || position.id || null); setCorrectedSegment('') }}>纠正环节 ↗</button></div>
                    {correctingId === (position.position_id || position.id) && <div className="correction"><label htmlFor={'correct-' + index}>改为</label><select id={'correct-' + index} value={correctedSegment} onChange={event => setCorrectedSegment(event.target.value)}><option value="">选择目标环节</option>{chain?.segments.filter(item => item.segment_id !== position.segment_id).map(item => <option key={item.segment_id} value={item.segment_id}>{item.segment_name}</option>)}</select><button type="button" className="button accent" disabled={!correctedSegment || Boolean(verifyBusy)} onClick={() => verify(position, 'correct')}>提交纠正</button><button type="button" className="button quiet" onClick={() => setCorrectingId(null)}>取消</button></div>}
                  </div>
                </article>)}
              </div>}
            </section>

            <div className="dual-grid"><section className="section worth-section"><SectionHeading index="02" eyebrow="CHAIN VALUE" title="值多少" note="仅核验的现有环节进入价值计算。" />
              {profile.worth?.icv_score == null ? <Empty title="暂不计算环节价值" detail={profile.where.abstained ? '定位弃权，待补充事实。' : '关键数据未齐备或环节尚未核验。'} /> : <><div className="value-hero"><div className="metric-label">ICV · 演示综合价值分</div><div className="metric-number">{number(profile.worth.icv_score)}</div>{profile.worth.rank_in_segment != null && <div className="metric-foot">环节内第 {profile.worth.rank_in_segment} 位 · 仅模拟样本</div>}</div><div className="factor-list"><div><span>环节价值 <small>SV</small></span><strong>{number(profile.worth.segment_sv)}</strong></div><div><span>企业竞争力 <small>CF</small></span><strong>{number(profile.worth.firm_cf)}</strong></div><div><span>风险折减 <small>RD</small></span><strong>{number(profile.worth.risk_rd, 2)}</strong></div></div><div className="dimension-list"><div className="dimension-heading"><span>环节价值维度</span><small>演示配置 / 0–100</small></div>{Object.entries(profile.worth.sv_dimensions || {}).map(([key, value]) => <div className="dimension-row" key={key}><span>{dimensionNames[key] || key}</span><span className="dimension-track"><i style={{ width: value == null ? '0%' : Math.max(0, Math.min(100, value)) + '%' }} /></span><strong>{number(value, 0)}</strong></div>)}{Object.keys(profile.worth.sv_dimensions || {}).length === 0 && <p className="muted">暂未获取维度数据</p>}</div><div className="formula-note">ICV = 环节价值 × 企业竞争力 × 风险折减</div></>}
            </section>

            <section className="section decision-section"><SectionHeading index="03" eyebrow="INVESTMENT SIGNAL" title="该不该动" note="规则驱动的招商研判，否决项优先。" />
              {profile.decision ? <><div className="decision-hero"><div><span className="metric-label">当前判断</span><strong>{state?.label}</strong><span className="decision-type">{profile.decision.decision_type === 'invest_promotion' ? '招商研判' : text(profile.decision.decision_type)}</span></div><div className="grade-box"><span>演示档位</span><b>{text(profile.decision.grade)}</b></div></div>
                {(profile.decision.vetoes || []).length > 0 && <div className="veto-box"><strong>否决项</strong>{profile.decision.vetoes?.map((item, index) => <span key={index}>{[item.rule_name, item.detail].filter(Boolean).join('：') || item.impact || '触发否决规则'}</span>)}</div>}
                {profile.data_stale && <div className="stale-box">数据已过期，请更新后再做招商档位判断。</div>}
                <div className="signal-list"><div><span>吸引力 · 演示分</span><strong>{number(profile.decision.attractiveness)}</strong></div><div><span>落地倾向 · 演示分</span><strong>{number(profile.decision.landing_prob)}</strong></div><div><span>载体匹配 · 演示分</span><strong>{number(profile.decision.carrier_match)}</strong></div></div></> : <Empty title="暂无招商判断" detail="定位或关键输入不足，等待补充数据。" />}
            </section></div>

            <section className="section ai-section" aria-label="AI 模型分析">
              <div className="ai-section-heading"><SectionHeading index="AI" eyebrow="ON-DEMAND MODEL ANALYSIS" title="AI 辅助分析" note="点击后使用当前企业的模拟画像生成解释，不会自动调用模型。" /><button type="button" className="button accent ai-run-button" onClick={runAiAnalysis} disabled={!selectedId || loadingProfile || aiLoadingFor === selectedId}>{aiLoadingFor === selectedId ? '正在分析…' : aiAnalysis?.enterpriseId === selectedId ? '重新分析' : '运行 AI 分析'}</button></div>
              <div className="ai-disclosure"><Pill tone="warn">输入为模拟数据</Pill><span>以下内容为模型生成，供辅助阅读；规则研判状态仍以现有画像为准。</span></div>
              {aiLoadingFor === selectedId && <div className="ai-loading" role="status">正在请求模型分析当前企业…</div>}
              {aiError?.enterpriseId === selectedId && <div className="ai-error" role="alert"><strong>AI 分析未完成</strong><p>{aiError.message}</p></div>}
              {aiAnalysis?.enterpriseId === selectedId && <div className="ai-result" aria-live="polite">
                <div className="ai-result-meta"><span>模型生成 · {text(aiAnalysis.result.model)}</span><span>{text(aiAnalysis.result.generated_at)}</span><Pill>{aiDecisionLabel(aiAnalysis.result.decision_status)}</Pill></div>
                <div className="ai-summary"><h3>分析摘要 · 模型生成</h3><p>{aiAnalysis.result.summary}</p></div>
                <div className="ai-result-grid">
                  <div><h3>主要发现 · 模型生成</h3>{aiAnalysis.result.findings.length ? <ul>{aiAnalysis.result.findings.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p className="muted">模型未返回发现项</p>}</div>
                  <div><h3>建议动作 · 模型生成</h3>{aiAnalysis.result.suggested_actions.length ? <ul>{aiAnalysis.result.suggested_actions.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p className="muted">模型未返回建议</p>}</div>
                </div>
                <div className="ai-limitations"><h3>适用边界</h3><ul>{aiAnalysis.result.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul><p>本次输入数据模式：{aiAnalysis.result.data_mode}。分析仅基于当前演示画像，不代表真实企业尽调结论。</p></div>
              </div>}
            </section>

            <section className="section explanation-section"><SectionHeading index="04" eyebrow="EVIDENCE TRAIL" title="凭什么" note="每条判断可回溯至模拟事实、来源和日期。" />
              {profile.explanation && <div className="conclusion"><span className="quote-mark">“</span><p>{text(profile.explanation.conclusion)}</p>{profile.explanation.score_summary && <small>{profile.explanation.score_summary.summary_text || '价值分 ' + number(profile.explanation.score_summary.score) + (profile.explanation.score_summary.rank_in_segment == null ? '' : ' · 环节内第 ' + profile.explanation.score_summary.rank_in_segment + ' 位')}</small>}</div>}
              <div className="reason-grid"><div><h3>主要驱动</h3>{(profile.explanation?.drivers || []).length ? <ul>{profile.explanation?.drivers?.map((item, index) => <li key={index}>{item.human_readable_explanation || item.factor_name || '演示规则因子'}{item.contribution == null ? '' : '（贡献 ' + number(item.contribution, 3) + '）'}</li>)}</ul> : <p className="muted">暂未获取</p>}</div><div><h3>数据缺口与下一步</h3>{(profile.explanation?.data_gaps || profile.data_gaps || profile.where.missing_signals || []).length ? <ul>{(profile.explanation?.data_gaps || profile.data_gaps || profile.where.missing_signals || []).map((item, index) => <li key={index}>{gapText(item)}</li>)}</ul> : <p className="muted">暂未获取</p>}{(profile.explanation?.suggested_actions || []).length > 0 && <div className="action-note">建议：{profile.explanation?.suggested_actions?.join('；')}</div>}</div></div>
              <div className="evidence-heading"><h3>原始证据</h3><span>字段 / 原文 / 来源 / 日期</span></div>
              {evidenceRows.length === 0 ? <Empty title="暂未获取可回查证据" /> : <div className="evidence-table" role="table" aria-label="原始证据"><div className="evidence-row table-head" role="row"><span role="columnheader">环节与字段</span><span role="columnheader">原文</span><span role="columnheader">来源 / 日期</span></div>{evidenceRows.map(({ evidence, label, key }) => <div className="evidence-row" role="row" key={key}><span role="cell"><strong>{label}</strong><small>{evidence.field_path}</small></span><span role="cell">{evidence.field_value == null ? '暂未获取' : String(evidence.field_value)}</span><span role="cell"><strong>{text(evidence.source)}</strong><small>{text(evidence.as_of)}</small></span></div>)}</div>}
            </section>
          </>}
        </> : <>
          <div className="page-intro graph-intro"><div><div className="eyebrow">INDUSTRIAL CHAIN MAP / 02</div><h1>{chain?.chain_name || '产业链图谱'}</h1><p>沿链条识别本地基础、缺口与可反查企业。</p></div><div className="intro-meta"><Pill tone="warn">模拟图谱</Pill><span>数据截至 {text(chain?.data_as_of)}</span></div></div>
          {loadingChain && <div className="loading-block">正在加载产业链图谱 <span className="loading-dots">···</span></div>}
          {chainError && <div className="error-block"><strong>图谱暂时无法加载</strong><p>{chainError}</p><button type="button" className="button quiet" onClick={() => setRefresh(value => value + 1)}>重试</button></div>}
          {chain && !loadingChain && <><div className="graph-summary"><div><span>覆盖环节</span><strong>{chain.segments.length.toString().padStart(2, '0')}</strong></div><div><span>本地企业</span><strong>{chain.segments.reduce((sum, item) => sum + (item.local_firm_count || 0), 0).toString().padStart(2, '0')}</strong></div><div><span>区域编码</span><strong className="summary-text">{text(chain.region_code)}</strong></div><div><span>统计期</span><strong className="summary-text">{text(chain.period)}</strong></div></div>
            <section className="section graph-section"><SectionHeading index="A" eyebrow="CHAIN TOPOLOGY" title="链条环节" note="点击环节查看本地企业和模拟缺口；状态反映演示样本。" />
              {chain.segments.length === 0 ? <Empty title="暂未获取链条环节" /> : <div className="segment-flow">{chain.segments.map((item, index) => <button type="button" key={item.segment_id} className={selectedSegment === item.segment_id ? 'segment-node active' : 'segment-node'} onClick={() => setSelectedSegment(item.segment_id)} aria-pressed={selectedSegment === item.segment_id}><span className="segment-order">{String(index + 1).padStart(2, '0')}</span><strong>{item.segment_name}</strong><small>{healthLabel(item.health_status)}</small><span className="node-bottom"><span>{item.local_firm_count == null ? '暂未获取' : item.local_firm_count + ' 家企业'}</span><span aria-hidden="true">↗</span></span></button>)}</div>}
            </section>
            {currentSegment && <div className="segment-detail-header"><div><div className="eyebrow">SELECTED SEGMENT / {selectedSegment}</div><h2>{currentSegment.segment_name}</h2><p>{healthLabel(currentSegment.health_status)} · {gapLevel(currentSegment.gap_level)}</p></div><Pill tone={currentSegment.has_leader ? 'good' : 'warn'}>{currentSegment.has_leader ? '有龙头企业' : '龙头待补'}</Pill></div>}
            {loadingSegment && <div className="loading-block compact">正在加载环节详情 ···</div>}
            {segmentError && <div className="error-block compact"><strong>环节详情暂时无法加载</strong><p>{segmentError}</p></div>}
            {currentSegment && !loadingSegment && !segmentError && <div className="dual-grid graph-details"><section className="section"><SectionHeading index="B" eyebrow="LOCAL FIRMS" title="环节企业" note="点击企业返回画像，查看定位证据。" />
              {segmentEnterprises.length === 0 ? <Empty title="暂无关联企业" detail="演示样本中未发现可展示的企业。" /> : <div className="related-list">{segmentEnterprises.map((item, index) => <button type="button" key={item.enterprise_id || item.id || index} onClick={() => (item.enterprise_id || item.id) && openEnterprise(item.enterprise_id || item.id || '')}><span className="related-index">{String(index + 1).padStart(2, '0')}</span><span><strong>{item.enterprise_name || item.name || '未命名企业'}</strong><small>{item.match_level === 'potential' ? '潜在方向 · 待核验' : item.match_level === 'primary' ? '主营环节' : item.match_level === 'secondary' ? '次要环节' : '定位待核验'} · {item.score_kind?.startsWith('manual') ? '人工核验指示值' : '未校准规则分'} {number(item.match_score, 2)}</small></span><span className="related-arrow">↗</span></button>)}</div>}
            </section><section className="section gap-section"><SectionHeading index="C" eyebrow="GAP ANALYSIS" title="模拟缺口" note="基于样本配置的缺口提示，不代表真实区域统计。" />
              {gap ? <><div className="gap-hero"><span>缺口级别</span><strong>{gapLevel(gap.gap_level)}</strong></div><div className="factor-list"><div><span>本地企业</span><strong>{gap.local_firm_count == null ? '暂未获取' : gap.local_firm_count + ' 家'}</strong></div><div><span>预期企业</span><strong>{gap.expected_firm_count == null ? '暂未获取' : gap.expected_firm_count + ' 家'}</strong></div></div><h3>待补层级</h3>{(gap.missing_tiers || []).length ? <div className="tag-list">{gap.missing_tiers?.map((tier, index) => <span key={index}>{tier}</span>)}</div> : <p className="muted">暂未获取</p>}<h3>跨区域候选</h3>{(gap.cross_region_candidates || []).length ? <ul className="plain-list">{gap.cross_region_candidates?.map((candidate, index) => <li key={candidate.enterprise_id || index}><strong>{candidate.enterprise_name}</strong> · {text(candidate.home_region)} · 演示价值分 {number(candidate.icv_score)}{candidate.top_reason ? ' · ' + candidate.top_reason : ''}</li>)}</ul> : <p className="muted">暂未获取</p>}</> : <Empty title="暂未获取缺口分析" />}
            </section></div>}
          </>}
        </>}
        <footer className="footer"><span>链脉 / 企业画像 × 产业链图谱</span><span>演示模拟数据 · 规则分未校准 · 不构成投资建议</span></footer>
      </main>
    </div>
  </div>
}
