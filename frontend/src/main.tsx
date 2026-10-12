import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Health = {ac_ready: boolean; verified_rules: number; reason: string | null};
type Source = {id: string; physical_page: number | null; section: string; quote: string; source_url: string; document_sha256: string};
type Result = {ac: number; rule_id: string; rule_version: number; trace: string[]; sources: Source[]};

function App() {
  const [health,setHealth] = useState<Health | null>(null);
  const [dex,setDex] = useState("14");
  const [busy,setBusy] = useState(false);
  const [result,setResult] = useState<Result | null>(null);
  const [error,setError] = useState("");
  useEffect(() => {
    fetch("/api/health").then(async r => {
      if (!r.ok) throw new Error("后端连接失败");
      setHealth(await r.json() as Health);
    }).catch(e => setError(String(e)));
  }, []);
  async function calculate() {
    setError(""); setResult(null);
    const score = Number(dex);
    if (!Number.isInteger(score) || score < 1 || score > 30) { setError("敏捷必须是 1–30 的整数"); return; }
    setBusy(true);
    try {
      const response = await fetch("/api/evaluate/ac", {method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({abilities:{dexterity:score},equipment:{armor:"leather",shield:false,alternative_ac:false}})});
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
      setResult(body as Result);
    } catch(e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <main>
    <p className="eyebrow">RULEFORGE / M1</p>
    <h1>每一次计算，都有出处。</h1>
    <p>SRD 5.1 · 真实文档解析与受限规则引擎</p>
    <section><h2>证据状态</h2>
      <p role="status">{health ? health.ac_ready ? "AC 规则证据已验证" : "AC 规则尚未就绪" : "正在连接后端…"}</p>
      {health?.reason && <p>{health.reason}</p>}
    </section>
    <section><h2>皮甲 AC</h2><p>仅适用：皮甲、无盾牌、无替代 AC 公式。</p>
      <label htmlFor="dex">敏捷属性值</label>
      <input id="dex" type="number" min="1" max="30" step="1" value={dex} onChange={e=>{setDex(e.target.value);setResult(null);}} />
      <button disabled={!health?.ac_ready || busy} onClick={calculate}>{busy ? "验证与计算中…" : "计算并查看来源"}</button>
      {error && <p role="alert">{error}</p>}
      {result && <article><h3>AC {result.ac}</h3><p>{result.rule_id} · v{result.rule_version}</p>
        <ul>{result.trace.map((s,i)=><li key={i}>{s}</li>)}</ul>
        {result.sources.map(s=><div key={s.id}><h4>{s.section} · PDF 第 {s.physical_page ?? "未知"} 页</h4>
          {s.quote.startsWith("<table") ? <><p>皮甲（Leather）：11 + 敏捷调整值。</p><details><summary>原始表格证据</summary><pre className="raw">{s.quote}</pre></details></> : <blockquote>{s.quote}</blockquote>}
          <a href={s.physical_page ? "/api/source/pdf#page="+s.physical_page : s.source_url} target="_blank" rel="noreferrer">查看原文 PDF</a>
          <p className="hash">SHA-256: {s.document_sha256}</p></div>)}
      </article>}
    </section>
    <footer>人物创建、战斗执行与 Homebrew 导入尚未实现。<br/>包含 Wizards of the Coast LLC 的 SRD 5.1 内容，采用 CC BY 4.0。完整署名见项目 ATTRIBUTION.md。</footer>
  </main>;
}
createRoot(document.getElementById("root")!).render(<App />);
