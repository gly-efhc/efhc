import React, { useCallback, useEffect, useState } from "react";
import { useAuthSessionController } from "../../auth/AuthSessionProvider";
import { currentDemoSessionScope, isDemoBackendMode, sessionInfo } from "../../demo/session";
import { transportRequest } from "../../data/transport";

/** Operator console for the real Neon TEST backend. No local accounting. */
export default function NeonTestConsole(): React.JSX.Element {
  const auth = useAuthSessionController();
  const [password, setPassword] = useState("");
  const [visualKey, setVisualKey] = useState("");
  const [candidate, setCandidate] = useState("0000000002");
  const [amount, setAmount] = useState("100.00000000");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // Server independently denies guest/operator impersonation; the console also hides controls.
  const authorized = auth.status === "authenticated" && currentDemoSessionScope() === "operator" && Boolean(auth.context?.global_id);
  const visualOnly = auth.status === "authenticated" && currentDemoSessionScope() === "visual";
  useEffect(() => { if (auth.context?.global_id) setCandidate(auth.context.global_id); }, [auth.context?.global_id]);
  const call = useCallback(async (fn: () => Promise<unknown>) => {
    setBusy(true); setMessage("");
    try { setResult(await fn()); }
    catch (error) { setMessage(error instanceof Error ? error.message : "DEMO_TEST_FAILED"); }
    finally { setBusy(false); }
  }, []);
  if (!isDemoBackendMode()) return <main style={{padding:24}}>DEMO-backend не подключён. Выберите DATA_SOURCE=demo_backend.</main>;
  const style: React.CSSProperties = {padding: 10, borderRadius: 6};
  return (
    <main style={{maxWidth:920,margin:"0 auto",padding:"28px 16px 90px",display:"grid",gap:16}}>
      <h1>EFHC — DEMO backend / Neon TEST</h1>
      <p>Все бизнес-запросы обращаются к реальному тестовому API и таблицам Neon. Данные браузерной симуляции не используются.</p>
      <section style={{display:"flex",gap:8,flexWrap:"wrap"}}>
        <input type="password" autoComplete="off" placeholder="Пароль TEST оператора" value={password} onChange={event=>setPassword(event.target.value)} style={style} />
        <button style={style} disabled={busy} onClick={()=>void call(async()=>{const ctx=await auth.loginDemo(password);setPassword("");return ctx;})}>Войти</button>
        <button style={style} disabled={busy} onClick={()=>void call(async()=>{await auth.logout();return {logged_out:true};})}>Выйти</button>
        <button style={style} disabled={busy} onClick={()=>void call(sessionInfo)}>Сессия</button>
      </section>
      <section style={{display:"grid",gap:10,border:"1px solid #9995",borderRadius:10,padding:16}}>
        <strong>Временный доступ для разработки интерфейса Admin</strong>
        <p>Только просмотр макетов административных страниц. Полномочия SuperAdmin, доступ к административным данным и операции изменения не предоставляются.</p>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <input type="password" autoComplete="off" aria-label="Временный ключ просмотра Admin" placeholder="Ключ просмотра Admin" value={visualKey} onChange={event=>setVisualKey(event.target.value)} style={{...style,minWidth:240,flex:"1"}} />
          <button style={style} disabled={busy || !visualKey} onClick={()=>void call(async()=>{
            const ctx=await auth.loginDemoVisual(visualKey);
            setVisualKey("");
            return {visual_preview:true,global_id:ctx.global_id,readonly:true};
          })}>Войти для просмотра</button>
        </div>
        {visualOnly ? <a href="/admin" style={{fontWeight:700}}>Открыть страницы Admin (только интерфейс)</a> : null}
      </section>
      <section style={{display:"flex",gap:8,flexWrap:"wrap"}}>
        <input style={style} value={candidate} onChange={event=>setCandidate(event.target.value)} maxLength={10} aria-label="Global ID" />
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(async()=>auth.selectDemoGlobalId(candidate))}>Выбрать Global ID</button>
        <span>Авторизован: {authorized ? auth.context?.global_id : "нет"}</span>
      </section>
      <section style={{display:"flex",gap:8,flexWrap:"wrap"}}>
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/staging/schema","GET"))}>Проверить таблицы</button>
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/staging/routes","GET"))}>Маршруты</button>
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/sync/me?fresh=1","POST"))}>Главная / данные Neon</button>
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/staging/bank-snapshot","GET"))}>Банк</button>
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/wallets/tonconnect/proof-payload","GET"))}>TonConnect payload</button>
      </section>
      <section style={{display:"flex",gap:8,flexWrap:"wrap"}}>
        <input style={style} value={amount} onChange={event=>setAmount(event.target.value)} aria-label="Тестовое пополнение EFHC" />
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/staging/topup","POST",{body:{amount_efhc:amount},idempotencyKey:globalThis.crypto.randomUUID()}))}>Тестовое пополнение через банк</button>
        <button style={style} disabled={busy || !authorized} onClick={()=>void call(()=>transportRequest("/staging/energy/tick","POST"))}>Генерация энергии</button>
      </section>
      {message ? <p role="alert">{message}</p> : null}
      <pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere",maxHeight:480,overflowY:"auto"}}>{JSON.stringify(result,null,2)}</pre>
    </main>
  );
}
