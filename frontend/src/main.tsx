import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Management, Audit, Evaluation } from "./Admin";
import { api } from "./client";
import type { Answer, Demo, Doc, Person, Ref } from "./client";
import "./style.css";

const pages = [
  "知识问答",
  "可读文档",
  "问答历史",
  "文档与授权",
  "审计记录",
  "安全评测",
];
const hints = [
  "访客登记点在哪里？",
  "薪酬复核的内部校验码是什么？",
  "星桥发布的验收口令是什么？",
];
const icons = ["⌕", "▤", "◷", "⊞", "≣", "◈"];
function Brand() {
  return (
    <div className="brand">
      <span className="mark" aria-hidden="true">
        ◫
      </span>
      <span>
        青屿知识库<small>SECURE ENTERPRISE RAG</small>
      </span>
    </div>
  );
}
function Sources({ refs }: { refs: Ref[] }) {
  return (
    <div className="sources">
      {refs.map((r) => (
        <a key={r.id} href={"/source/" + encodeURIComponent(r.id)}>
          ▤　{r.title} <small>{r.id} ↗</small>
        </a>
      ))}
    </div>
  );
}

function Ask({ docs, me }: { docs: Doc[]; me: Person }) {
  const [q, setQ] = useState(""),
    [answer, setAnswer] = useState<Answer>(),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setAnswer(undefined);
    setErr("");
    try {
      setAnswer(await api("/query", "POST", { question: q }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="facts">
        <div>
          <span>可读文档</span>
          <strong>
            {docs.length}
            <small> 篇</small>
          </strong>
        </div>
        <div>
          <span>当前部门</span>
          <strong>{me.dept}</strong>
        </div>
        <div>
          <span>权限版本</span>
          <strong>E{me.epoch}</strong>
        </div>
      </div>
      <section className="panel ask">
        <h2>向知识库提问</h2>
        <p className="sub">回答将附上你当前有权查看的来源。</p>
        <form onSubmit={search}>
          <label className="sr" htmlFor="question">
            问题
          </label>
          <textarea
            id="question"
            value={q}
            maxLength={1000}
            onChange={(e) => setQ(e.target.value)}
            placeholder="输入问题，例如：访客登记点在哪里？"
          />
          <div className="submit">
            <small>{q.length} / 1000</small>
            <button disabled={busy || !q.trim()}>
              {busy ? "正在检索…" : "检索并回答　↗"}
            </button>
          </div>
        </form>
        <div className="suggestions">
          {hints.map((h) => (
            <button className="chip" key={h} onClick={() => setQ(h)}>
              {h}
            </button>
          ))}
        </div>
      </section>
      {err && <p role="alert">{err}</p>}
      {answer && (
        <section className="panel result" aria-live="polite">
          <div className="section-head">
            <h2>回答</h2>
            <span className="status">
              {answer.cached
                ? "缓存已复核"
                : answer.refs.length
                  ? "已检索"
                  : "资料不足"}
            </span>
          </div>
          <p className="answer">{answer.answer}</p>
          <Sources refs={answer.refs} />
          <small>
            {answer.ms} ms　·　{answer.model}　·　E{answer.epoch}
          </small>
        </section>
      )}
    </>
  );
}
function Catalog({ docs }: { docs: Doc[] }) {
  const [filter, set] = useState("");
  return (
    <section className="panel">
      <label>
        筛选可读文档
        <input
          placeholder="标题或文档 ID"
          value={filter}
          onChange={(e) => set(e.target.value)}
        />
      </label>
      {docs
        .filter((d) =>
          (d.id + d.title).toLowerCase().includes(filter.toLowerCase()),
        )
        .map((d) => (
          <article className="doc" key={d.id}>
            <div>
              <small>
                {d.id} / v{d.version}
              </small>
              <h3>{d.title}</h3>
            </div>
            <span>{d.reason}</span>
            <a
              href={
                "/api/documents/" +
                d.id +
                "/versions/" +
                d.version +
                "/download"
              }
            >
              下载
            </a>
          </article>
        ))}
    </section>
  );
}
function History() {
  const [rows, set] = useState<(Answer & { question: string })[]>([]),
    [msg, setMsg] = useState("正在读取…");
  useEffect(() => {
    api<(Answer & { question: string })[]>("/history")
      .then((r) => {
        set(r);
        setMsg(r.length ? "" : "当前权限版本下暂无问答记录。");
      })
      .catch((e) => setMsg(e.message));
  }, []);
  return (
    <section className="panel">
      <h2>最近问答</h2>
      <p>{msg}</p>
      {rows.map((r) => (
        <details key={r.id}>
          <summary>{r.question}</summary>
          <p className="answer">{r.answer}</p>
          <Sources refs={r.refs} />
        </details>
      ))}
    </section>
  );
}
function Source({ id }: { id: string }) {
  const [r, set] = useState<Ref>(),
    [msg, err] = useState("正在复核权限…");
  useEffect(() => {
    api<Ref>("/references/" + encodeURIComponent(id))
      .then(set)
      .catch((e) => err(e.message));
  }, [id]);
  return (
    <section className="panel">
      <h2>{r ? r.title : "引用详情"}</h2>
      {r ? (
        <>
          <p className="meta">
            {r.id} · 页 {r.page} · 字符 {r.start}–{r.end} · 规则 v
            {r.acl_version}
          </p>
          <pre>{r.body}</pre>
          <a
            href={
              "/api/documents/" + r.doc + "/versions/" + r.version + "/download"
            }
          >
            下载此版本原文
          </a>
        </>
      ) : (
        <p>{msg}</p>
      )}
    </section>
  );
}

function App() {
  const [demo, setDemo] = useState<Demo>(),
    [me, setMe] = useState<Person>(),
    [loaded, ready] = useState(false);
  const [uid, setUid] = useState("employee"),
    [pwd, setPwd] = useState(""),
    [error, err] = useState(""),
    [page, go] = useState(0);
  const [docs, setDocs] = useState<Doc[]>([]),
    [rev, bump] = useState(0);
  const [source, setSource] = useState(
    location.pathname.split("/source/")[1] || "",
  );
  useEffect(() => {
    api<Demo>("/demo")
      .then((d) => {
        setDemo(d);
        setPwd(d.password);
      })
      .catch((e) => err(e.message));
    api<Person>("/me")
      .then(setMe)
      .catch(() => {})
      .finally(() => ready(true));
  }, []);
  useEffect(() => {
    if (!me) return;
    let live = true;
    async function sync() {
      try {
        const next = await api<Person>("/me");
        if (live)
          setMe((old) =>
            old?.uid === next.uid && old.epoch === next.epoch ? old : next,
          );
      } catch {
        if (live) setMe(undefined);
      }
    }
    const timer = setInterval(sync, 2000);
    window.addEventListener("focus", sync);
    window.addEventListener("pageshow", sync);
    return () => {
      live = false;
      clearInterval(timer);
      window.removeEventListener("focus", sync);
      window.removeEventListener("pageshow", sync);
    };
  }, [me?.uid]);
  useEffect(() => {
    let live = true;
    setDocs([]);
    if (me)
      api<Doc[]>("/documents")
        .then((ds) => {
          if (live) setDocs(ds);
        })
        .catch((e) => err(e.message));
    return () => {
      live = false;
    };
  }, [me?.uid, me?.epoch, rev]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/login", "POST", { username: uid, password: pwd });
      setMe(await api("/me"));
      go(0);
      err("");
    } catch (e) {
      err((e as Error).message);
    }
  }
  if (!loaded) return <main>正在连接本地知识库…</main>;
  if (!me)
    return (
      <div className="login">
        <div className="login-story">
          <Brand />
          <div className="cover">
            <span className="book" aria-hidden="true"></span>
          </div>
          <div>
            <h1>企业知识库</h1>
            <p>文档检索、来源追溯与访问授权</p>
          </div>
        </div>
        <form className="login-form" onSubmit={login}>
          <small>本地演示工作区</small>
          <h2>登录知识库</h2>
          <label>
            演示账号
            <select value={uid} onChange={(e) => setUid(e.target.value)}>
              {demo?.accounts.map((a) => (
                <option key={a.uid} value={a.uid}>
                  {a.name} · {a.role}（{a.uid}）
                </option>
              ))}
            </select>
          </label>
          <label>
            演示口令
            <input
              type="password"
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
            />
          </label>
          <button disabled={!demo}>进入工作区　→</button>
          <p className="meta">合成企业账号 · 演示口令已预填</p>
          <p role="alert">{error}</p>
        </form>
      </div>
    );
  const titles = me.role === "管理员" ? pages : pages.slice(0, 3);
  const active = titles[page] ? page : 0;
  return (
    <div className="shell">
      <aside>
        <Brand />
        <nav aria-label="工作区导航">
          {titles.map((p, i) => (
            <button
              className={i === active && !source ? "active" : ""}
              key={p}
              onClick={() => {
                if (source) {
                  history.replaceState(null, "", "/");
                  setSource("");
                }
                go(i);
                err("");
              }}
            >
              <span aria-hidden="true">{icons[i]}</span>
              {p}
            </button>
          ))}
        </nav>
        <div className="profile">
          <b>
            {me.name} · {me.role}
          </b>
          <small>
            {me.uid} / {me.dept}
          </small>
          <button
            className="signout"
            onClick={async () => {
              try {
                await api("/logout", "POST");
                setMe(undefined);
                setDocs([]);
                err("");
              } catch (e) {
                err((e as Error).message);
              }
            }}
          >
            退出登录
          </button>
        </div>
      </aside>
      <main>
        <header>
          <small>青屿 / 企业工作区</small>
          <span>{me.model}</span>
        </header>
        <div className="heading">
          <h1>{source ? "引用详情" : titles[active]}</h1>
          <p>
            {source
              ? "检查当前权限并读取指定版本的来源片段。"
              : [
                  "查询合成企业资料，查看答案背后的文档依据。",
                  "查看当前身份可以读取的资料和授权原因。",
                  "查看当前授权版本内保存的问答。",
                  "维护文档版本、部门访问与个人授权。",
                  "按请求核对授权决策、来源和执行状态。",
                  "比较相同资料和问题下的安全性与可用性。",
                ][active]}
          </p>
        </div>
        {error && <p role="alert">{error}</p>}
        <div
          key={me.uid + ":" + (active === 3 && !source ? "manage" : me.epoch)}
        >
          {source ? (
            <>
              <Source id={source} />
              <p>
                <a href="/">返回知识问答</a>
              </p>
            </>
          ) : active === 0 ? (
            <Ask docs={docs} me={me} />
          ) : active === 1 ? (
            <Catalog docs={docs} />
          ) : active === 2 ? (
            <History />
          ) : active === 3 && demo ? (
            <Management demo={demo} changed={() => bump((r) => r + 1)} />
          ) : active === 4 ? (
            <Audit />
          ) : (
            <Evaluation />
          )}
        </div>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
