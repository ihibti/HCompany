import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

interface TopicSpec { topic: string; keywords: string[]; example_creators: string[] }
interface Profile {
  id: string; summary: string; languages: string[];
  include: TopicSpec[]; exclude: { topic: string; keywords: string[] }[];
  sources: { name: string; url: string }[];
}
interface Job { id: string; kind: string; platform: string; status: string; agent_view_url?: string | null; error?: string | null; result?: { logged_in?: boolean; account_label?: string; items?: { url: string; title_or_caption: string; creator: string; why: string }[]; actions?: { kind?: string; video_url?: string; title?: string; ok: boolean; note?: string }[] } }
interface Health { keys: Record<string, boolean>; models: { fast: string; smart: string }; fake_ai: boolean }
interface Counters { auto: number; manual: number; undone: number; replaced?: number }

const PLATFORMS = ["youtube", "tiktok", "instagram"] as const;
const STATUS_FR: Record<string, string> = { queued: "en file", running: "en cours", completed: "terminé", failed: "échoué", timed_out: "expiré", interrupted: "interrompu" };

function useBackend() {
  const [base, setBase] = useState("http://localhost:8787");
  useEffect(() => { chrome.storage.local.get("backendUrl").then((s) => { const v = s.backendUrl as string | undefined; if (v) setBase(v); }); }, []);
  const call = async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const r = await fetch(base + path, init);
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<T>;
  };
  return { base, setBase: async (b: string) => { setBase(b); await chrome.storage.local.set({ backendUrl: b }); }, call };
}

function MiniMascot() {
  const ref = React.useRef<HTMLSpanElement>(null);
  useEffect(() => {
    import("../overlay/character").then((m) => { if (ref.current) ref.current.innerHTML = m.CHAR_SVG; });
  }, []);
  return <span ref={ref} style={{ width: 34, display: "inline-block", verticalAlign: "-8px" }} />;
}

function ActiveTab() {
  const [plat, setPlat] = useState("");
  useEffect(() => {
    chrome.tabs?.query({ active: true, currentWindow: true }).then((t) => {
      const u = t[0]?.url ?? "";
      setPlat(u.includes("youtube") ? "youtube" : u.includes("tiktok") ? "tiktok" : u.includes("instagram") ? "instagram" : "");
    }).catch(() => {});
  }, []);
  return plat ? <small className="mut">(onglet : {plat})</small> : null;
}

function App() {
  const { base, setBase, call } = useBackend();
  const [health, setHealth] = useState<Health | null>(null);
  const [text, setText] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const [counters, setCounters] = useState<Counters>({ auto: 0, manual: 0, undone: 0 });
  const [autoThrow, setAutoThrow] = useState(true);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({ youtube: true, tiktok: true, instagram: true });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState("");

  useEffect(() => {
    call<Health>("/health").then(setHealth).catch(() => setHealth(null));
    chrome.storage.local.get(["profile", "profileId", "counters", "autoThrow", "enabled"]).then((s) => {
      const x = s as Record<string, any>;
      if (x.profile) setProfile(x.profile);
      if (x.counters) setCounters(x.counters);
      if (x.autoThrow !== undefined) setAutoThrow(x.autoThrow);
      if (x.enabled) setEnabled(x.enabled);
    });
    const t = setInterval(() => call<Job[]>("/jobs").then(setJobs).catch(() => {}), 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  const STEPS: Record<string, string> = { holo: "Je lis tes envies…", linkup: "Je cherche sur le web (Linkup)…", done: "Profil prêt" };

  async function createProfile() {
    setBusy(true); setErr("");
    const pid = Math.random().toString(36).slice(2, 12);
    const iv = setInterval(() => {
      call<{ step: string }>(`/profile_progress/${pid}`).then((r) => setProgress(STEPS[r.step] ?? r.step)).catch(() => {});
    }, 700);
    try {
      const p = await call<Profile>("/profile", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, progress_id: pid }) });
      setProfile(p);
      await chrome.storage.local.set({ profile: p, profileId: p.id });
    } catch (e) { setErr(e instanceof Error ? e.message : "Erreur"); }
    clearInterval(iv);
    setProgress("");
    setBusy(false);
  }

  const [trainActions, setTrainActions] = useState({ not_interested: true, search_watch: true, like: true });
  const [autoTrain, setAutoTrain] = useState(false);
  const [trainEvery, setTrainEvery] = useState(15);
  const [replaceHome, setReplaceHome] = useState(false);
  useEffect(() => { chrome.storage.local.get(["trainActions","autoTrain","trainEvery","replaceHome"]).then((x)=>{ const s=x as Record<string,any>; if(s.trainActions)setTrainActions(s.trainActions); if(s.autoTrain!==undefined)setAutoTrain(s.autoTrain); if(s.trainEvery)setTrainEvery(s.trainEvery); setReplaceHome(!!s.replaceHome); }); }, []);

  async function postJob(path: string, platform: string) {
    if (!profile) { setErr("Crée d'abord un profil."); return; }
    setErr("");
    try {
      const body = path === "/login" ? { platform } : { profile_id: profile.id, platform, actions: trainActions };
      await call<Job>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setJobs(await call<Job[]>("/jobs"));
    } catch (e) { setErr(e instanceof Error ? e.message : "Erreur"); }
  }

  return (
    <div className="app">
      <h1><MiniMascot />Tomate</h1>
      {health?.fake_ai && <div style={{background:"#c0392b",color:"#fff",borderRadius:8,padding:"8px 12px",fontWeight:700}}>MODE SIMULÉ — rien n'est envoyé à H ni à Holo</div>}
      {health && !health.fake_ai && <small className="mut">backend {base.replace("http://", "")} — H {health.keys.hai ? "✓" : "✗"} Linkup {health.keys.linkup ? "✓" : "✗"}</small>}
      <div>
        <h2>Backend</h2>
        <input type="text" value={base} onChange={(e) => void setBase(e.target.value)} />
      </div>
      <div>
        <h2>Ce que je veux voir</h2>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Ex : de l'escalade et de la cuisine japonaise, pas de drama ni de gaming" />
        <button onClick={createProfile} disabled={busy || !text.trim()} style={{ marginTop: 8 }}>Créer mon profil</button>
        {progress && <small className="mut" style={{ display: "block", marginTop: 6 }}>{progress}</small>}
      </div>
      {profile && (
        <div>
          <h2>Mon profil</h2>
          <p>{profile.summary}</p>
          <div>{profile.include.map((t) => <span key={t.topic} className="chip inc">{t.topic}</span>)}
            {profile.exclude.map((t) => <span key={t.topic} className="chip exc">{t.topic}</span>)}</div>
          {profile.include.flatMap((t) => t.example_creators).length > 0 && (
            <small className="mut">Créateurs de référence : {profile.include.flatMap((t) => t.example_creators).join(", ")}</small>)}
          {profile.sources?.length > 0 && (
            <small className="mut">Sources : {profile.sources.slice(0, 4).map((s, i) => <a key={i} href={s.url} target="_blank" rel="noreferrer">{s.name || s.url}</a>).reduce<React.ReactNode[]>((a, b) => a.length ? [...a, ", ", b] : [b], [])}</small>)}
        </div>
      )}
      <div>
        <h2>Réglages</h2>
        {PLATFORMS.map((p) => (
          <label key={p} className="row" style={{ display: "block" }}>
            <input type="checkbox" checked={enabled[p] !== false}
              onChange={(e) => { const n = { ...enabled, [p]: e.target.checked }; setEnabled(n); void chrome.storage.local.set({ enabled: n }); }} /> {p}
          </label>
        ))}
        <label className="row" style={{ display: "block" }}>
          <input type="checkbox" checked={autoThrow}
            onChange={(e) => { setAutoThrow(e.target.checked); void chrome.storage.local.set({ autoThrow: e.target.checked }); }} /> Lanceur automatique
        </label>
      </div>
      <div>
        <h2>Compteurs <ActiveTab /></h2>
        <span className="chip inc">{counters.auto} auto</span>
        <span className="chip exc">{counters.manual} à la main</span>
        <span className="chip">{counters.undone} annulées</span>
        <span className="chip inc">{counters.replaced ?? 0} remplacées</span>
      </div>
      {profile && (
        <div>
          <h2>Entraînement (actions autorisées)</h2>
          {([["not_interested","Pas intéressé"],["search_watch","Recherches + visionnages"],["like","Likes"]] as const).map(([k,label]) => (
            <label key={k} style={{display:"block"}}><input type="checkbox" checked={trainActions[k]}
              onChange={(e)=>{const n={...trainActions,[k]:e.target.checked};setTrainActions(n);void chrome.storage.local.set({trainActions:n});}}/> {label}</label>
          ))}
          <label style={{display:"block"}}><input type="checkbox" checked={autoTrain}
            onChange={(e)=>{setAutoTrain(e.target.checked);void chrome.storage.local.set({autoTrain:e.target.checked});}}/> Entraîner automatiquement toutes les <input type="text" value={trainEvery} onChange={(e)=>{const n=parseInt(e.target.value)||15;setTrainEvery(n);void chrome.storage.local.set({trainEvery:n});}} style={{width:36,display:"inline"}}/> tomates</label>
          <h2>Actions</h2>
          {PLATFORMS.map((p) => (
            <div className="row" key={p} style={{ marginBottom: 6 }}>
              <b style={{ width: 80 }}>{p}</b>
              <button className="ghost" disabled={health?.fake_ai} onClick={() => postJob("/train", p)}>Entraîner maintenant</button>
              <button className="ghost" disabled={health?.fake_ai} onClick={() => postJob("/scout", p)}>Chercher pour moi</button>
            </div>
          ))}
          <label style={{display:"block",marginTop:8}}><input type="checkbox" checked={replaceHome} onChange={(e)=>{setReplaceHome(e.target.checked);void chrome.storage.local.set({replaceHome:e.target.checked});}}/> Remplacer tout l'accueil YouTube par le feed Tomate</label>
          <small className="mut">H s'entraîne sur ton compte dans un Chrome séparé ; ton feed s'améliore partout où tu es connecté (l'algo met un peu de temps). Les remplacements Tomate, eux, sont immédiats.</small>
          <button className="ghost" disabled={health?.fake_ai} onClick={async () => { await call("/local/open-browser", { method: "POST" }); }}>Ouvrir le Chrome d'entraînement (pour me connecter)</button>
        </div>
      )}
      {err && <p style={{ color: "#c0392b" }}>{err}</p>}
      <div>
        <h2>Jobs de l'agent</h2>
        {jobs.length === 0 && <small className="mut">Aucun job.</small>}
        {[...jobs].reverse().map((j) => (
          <div className="job" key={j.id}>
            <b>{j.kind}</b> {j.platform && `· ${j.platform}`} — {STATUS_FR[j.status] ?? j.status}
            {j.agent_view_url && <> — <a href={j.agent_view_url} target="_blank" rel="noreferrer">Regarder l'agent</a></>}
            {j.error && <div style={{ color: "#c0392b" }}>{j.error}</div>}
            {j.result?.items?.map((it, i) => (
              <div className="scout" key={i}><a href={it.url} target="_blank" rel="noreferrer">{it.title_or_caption || it.url}</a> <small className="mut">{it.creator} — {it.why}</small></div>
            ))}
            {j.result?.logged_in !== undefined && <small className="mut"> — {j.result.logged_in ? `connecté (${j.result.account_label || "compte"})` : "non connecté"}</small>}
            {j.result?.actions?.map((a, i) => (
              <div key={i}><small className="mut">{a.ok ? "✓" : "✗"} {a.kind || ""} {a.title || a.video_url || ""} {a.note || ""}</small></div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
