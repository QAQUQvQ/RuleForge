import {useState} from 'react';

type Source={id:string;physical_page:number|null;printed_page:string|null;section_hierarchy:string[];json_pointer:string;quote:string};
type RecordEntry={id:string;record_version:number;canonical_name:string;record_type:string;review_status:string;validation_status:string};
type Search={items:{record:RecordEntry;matched_fields:string[]}[];total:number;view:string};
type Card={character:{id:string;name:string;version:number;abilities:typeof defaults;speed_ft:number;inventory:unknown[];hp:{maximum:number;current:number;temporary:number};proficiency_bonus:number};ability_modifiers:Record<string,number>};
type Preview={source_refs:Source[];attack:{hit:boolean;attack_total:number};damage:{total:number};hp:{after:{current:number;temporary:number}}};
const defaults={strength:16,dexterity:14,constitution:14,intelligence:10,wisdom:12,charisma:8};
const labels:Record<string,string>={strength:'力量',dexterity:'敏捷',constitution:'体质',intelligence:'智力',wisdom:'感知',charisma:'魅力'};
async function api<T>(path:string,body?:unknown,method='POST',token=''):Promise<T>{
  const r=await fetch('/api'+path,{method:body===undefined?'GET':method,
    headers:{'Content-Type':'application/json',...(token?{'X-RuleForge-Admin':token}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  const v=await r.json();if(!r.ok)throw new Error(v.error?`${v.error.code}: ${v.error.message}`:JSON.stringify(v.detail));return v as T;
}
function Json({value}:{value:unknown}){return <pre className="raw output">{JSON.stringify(value,null,2)}</pre>}
function Sources({sources}:{sources:Source[]}){return <>{sources.map(s=><details key={s.id}><summary>PDF {s.physical_page??'未知'} · 印刷页 {s.printed_page??'未知'} · {s.section_hierarchy.join(' / ')}</summary><p className="hash">{s.id}<br/>{s.json_pointer}</p><pre className="raw">{s.quote}</pre>{s.physical_page&&<a target="_blank" rel="noreferrer" href={'/api/source/pdf#page='+s.physical_page}>查看 PDF 原文</a>}</details>)}</>}

export function M2(){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [q,setQ]=useState(''),[kind,setKind]=useState(''),[admin,setAdmin]=useState(false),[token,setToken]=useState('');
  const [search,setSearch]=useState<Search|null>(null),[detail,setDetail]=useState<{record:RecordEntry;sources:Source[]}|null>(null);
  const [name,setName]=useState('Fighter'),[scores,setScores]=useState(defaults),[speed,setSpeed]=useState(30),[origin,setOrigin]=useState(false);
  const [card,setCard]=useState<Card|null>(null),[id,setId]=useState(''),[inventory,setInventory]=useState('[]'),[ac,setAC]=useState<unknown>(null);
  const [dice,setDice]=useState('15,6'),[mode,setMode]=useState('melee'),[distance,setDistance]=useState(5),[scene,setScene]=useState(false);
  const [adv,setAdv]=useState(false),[dis,setDis]=useState(false),[near,setNear]=useState(false),[targetAC,setTargetAC]=useState(14);
  const [hp,setHP]=useState(20),[temp,setTemp]=useState(2),[defense,setDefense]=useState('resistance'),[damageType,setDamageType]=useState('slashing');
  const [result,setResult]=useState<Preview|null>(null),[weapon,setWeapon]=useState('srd51.equipment.longsword');
  async function act(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn()}catch(e){setError(String(e))}finally{setBusy(false)}}
  function show(c:Card){setCard(c);setId(c.character.id);setName(c.character.name);setScores(c.character.abilities);setSpeed(c.character.speed_ft);setInventory(JSON.stringify(c.character.inventory,null,2));setAC(null);setResult(null)}
  return <div className="m2"><p className="eyebrow">M2 / 基础计算工作台</p>
    <p>正式数据需单独审核、发布与运行许可。隔离演示库使用模拟审核，固定骰子仅用于演示。此处不裁定回合和行动经济。</p>
    {error&&<p role="alert">{error}</p>}
    <fieldset disabled={busy}><section><h2>1 · 规则检索与证据</h2>
      <div className="row"><label>关键词或 ID<input className="wide" value={q} onChange={e=>setQ(e.target.value)}/></label>
      <label>分类<select value={kind} onChange={e=>setKind(e.target.value)}><option value="">全部</option>{['equipment','spell','class','condition','general_rule'].map(k=><option key={k}>{k}</option>)}</select></label>
      <button onClick={()=>act(async()=>setSearch(await api<Search>(`${admin?'/admin/catalog':'/search'}?q=${encodeURIComponent(q)}${kind?'&record_type='+kind:''}`,undefined,'GET',token)))}>搜索</button></div>
      <label><input type="checkbox" checked={admin} onChange={e=>setAdmin(e.target.checked)}/>管理视图：待审核候选不可执行</label>
      {admin&&<label>本地管理令牌<input type="password" className="wide" value={token} autoComplete="off" onChange={e=>setToken(e.target.value)}/></label>}
      {search&&<><p>{search.total} 条 · {search.view}</p>{search.items.map(({record:r,matched_fields:m})=><article key={r.id+':'+r.record_version}>
        <button className="linkbutton" onClick={()=>act(async()=>setDetail(await api(`${admin?'/admin':''}/catalog/${r.id}?version=${r.record_version}`,undefined,'GET',token)))}>{r.canonical_name} · v{r.record_version}</button>
        <p className="hash">{r.id} · {r.validation_status} / {r.review_status} · 匹配：{m.join(', ')}<br/>执行许可需独立验证</p></article>)}</>}
      {detail&&<><h3>{detail.record.canonical_name}</h3><Sources sources={detail.sources}/></>}
    </section>
    <section><h2>2 · 创建 1 级 Fighter</h2><p>职业选项：Defense，Athletics / Perception，锁子甲、长剑、盾牌、两把手斧、探索者背包。Second Wind 仅保存资源与参考。</p>
      <label>姓名<input className="wide" value={name} onChange={e=>setName(e.target.value)}/></label>
      <div className="scores">{Object.entries(scores).map(([k,v])=><label key={k}>{labels[k]}<input type="number" min={1} max={30} value={v} onChange={e=>setScores({...scores,[k]:Number(e.target.value)})}/></label>)}</div>
      <label>基础速度 ft<input type="number" min={0} max={1000} value={speed} onChange={e=>setSpeed(Number(e.target.value))}/></label>
      <p><label><input type="checkbox" checked={origin} onChange={e=>setOrigin(e.target.checked)}/>确认最终属性与基础速度；种族、背景另行处理</label></p>
      <button disabled={!origin} onClick={()=>act(async()=>show(await api<Card>('/characters',{name,abilities:scores,skills:['Athletics','Perception'],speed_ft:speed,origin_confirmed:true})))}>创建并保存</button>
      <div className="row"><label>角色 ID<input className="wide" value={id} onChange={e=>setId(e.target.value)}/></label><button onClick={()=>act(async()=>show(await api<Card>('/characters/'+encodeURIComponent(id))))}>读取</button></div>
      {card&&<><h3>{card.character.name} · v{card.character.version}</h3><p>HP {card.character.hp.current}/{card.character.hp.maximum} · 熟练 +{card.character.proficiency_bonus}</p><Json value={card.ability_modifiers}/>
      <button onClick={()=>act(async()=>show(await api<Card>('/characters/'+card.character.id,{expected_version:card.character.version,name,abilities:scores,speed_ft:speed},'PATCH')))}>保存表单中的姓名、属性与速度</button></>}
    </section>
    <section><h2>3 · 装备与 AC</h2><p>引用使用稳定 ID 与版本。body：护甲，main_hand：武器，off_hand：盾牌。卸下时设 equipped=false 与 inventory 槽位。普通无甲来源尚缺，计算会拒绝。</p>
      <label>装备清单 JSON<textarea rows={10} value={inventory} onChange={e=>setInventory(e.target.value)}/></label>
      <div className="row"><button disabled={!card} onClick={()=>act(async()=>{if(card)show(await api<Card>('/characters/'+card.character.id,{expected_version:card.character.version,inventory:JSON.parse(inventory)},'PATCH'))})}>保存装备</button>
      <button disabled={!card} onClick={()=>act(async()=>{if(card)setAC(await api('/characters/'+card.character.id+'/ac'))})}>计算 AC 与来源</button></div>{ac!==null&&<Json value={ac}/>}</section>
    <section><h2>4 · 攻击、伤害与隔离目标 HP</h2><p>固定骰子演示：命中才读取伤害骰，暴击读取双倍伤害骰。目标 AC、HP 与防御为 DM 输入，不代表自动识别了怪物特性。</p>
      <label>已装备武器 ID<input className="wide" value={weapon} onChange={e=>setWeapon(e.target.value)}/></label>
      <div className="row"><label>方式<select value={mode} onChange={e=>setMode(e.target.value)}><option value="melee">近战</option><option value="ranged">远程 / 投掷</option></select></label>
      <label>距离 ft<input type="number" value={distance} onChange={e=>setDistance(Number(e.target.value))}/></label><label>固定骰值<input className="wide" value={dice} onChange={e=>setDice(e.target.value)}/></label></div>
      <div className="row"><label><input type="checkbox" checked={adv} onChange={e=>setAdv(e.target.checked)}/>优势</label><label><input type="checkbox" checked={dis} onChange={e=>setDis(e.target.checked)}/>劣势</label><label><input type="checkbox" checked={near} onChange={e=>setNear(e.target.checked)}/>5 ft 内有能看见我的非失能敌人</label></div>
      <div className="row"><label>目标 AC<input type="number" value={targetAC} onChange={e=>setTargetAC(Number(e.target.value))}/></label><label>初始 / 最大 HP<input type="number" value={hp} onChange={e=>setHP(Number(e.target.value))}/></label><label>临时 HP<input type="number" value={temp} onChange={e=>setTemp(Number(e.target.value))}/></label></div>
      <div className="row"><label>防御<select value={defense} onChange={e=>setDefense(e.target.value)}><option value="none">无</option><option value="resistance">抗性</option><option value="vulnerability">易伤</option><option value="immunity">免疫</option></select></label><label>伤害类型<select value={damageType} onChange={e=>setDamageType(e.target.value)}>{['slashing','piercing','bludgeoning','fire','cold','poison'].map(t=><option key={t}>{t}</option>)}</select></label></div>
      <p><label><input type="checkbox" checked={scene} onChange={e=>setScene(e.target.checked)}/>确认目标可见、无遮挡、距离已核对且无其他特殊机制；目标数据仅作隔离演示</label></p>
      <button disabled={!card||!scene} onClick={()=>act(async()=>{if(card)setResult(await api<Preview>('/combat/preview',{attacker_id:card.character.id,expected_version:card.character.version,weapon_id:weapon,target_id:'isolated-target',target_ac:targetAC,target_hp:{maximum:hp,current:hp,temporary:temp},target_defenses:defense==='none'?{}:{[defense]:[damageType]},target_scope:'isolated_dm_input',fixed_dice:dice.split(',').map(s=>Number(s.trim())),context:{mode,distance_ft:distance,scene_confirmed:true,target_visible:true,cover:'none',hostile_within_5ft:near,advantage:adv,disadvantage:dis}}))})}>运行固定骰子演示</button>
      {result&&<><h3>{result.attack.hit?'命中':'失手'} · 攻击总值 {result.attack.attack_total} · 伤害 {result.damage.total}</h3><p>隔离 HP → {result.hp.after.current}；临时 HP → {result.hp.after.temporary}</p><details><summary>全部计算步骤与规则版本</summary><Json value={result}/></details><Sources sources={result.source_refs}/></>}
    </section></fieldset><p role="status">{busy?'正在核对来源与运行许可…':''}</p></div>
}
