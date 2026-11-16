import { useEffect, useState } from "react";
import { api, uploadData } from "./client";
import type { Demo, Doc } from "./client";

export function Management({
  demo,
  changed,
}: {
  demo: Demo;
  changed: () => void;
}) {
  const [docs, setDocs] = useState<Doc[]>([]),
    [selected, setSelected] = useState("RD-001"),
    [msg, setMsg] = useState("");
  const [title, setTitle] = useState(""),
    [dept, setDept] = useState("研发部"),
    [file, setFile] = useState<File>();
  const [publicRead, setPublic] = useState(false),
    [departments, setDepts] = useState<string[]>([]),
    [users, setUsers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false);
  const doc = docs.find((d) => d.id === selected);
  async function refresh() {
    setDocs(await api<Doc[]>("/admin/documents"));
  }
  useEffect(() => {
    refresh().catch((e) => setMsg(e.message));
  }, []);
  useEffect(() => {
    setPublic(Boolean(doc?.public));
    setDepts(doc?.departments || []);
    setUsers(doc?.users || []);
    setConfirm(false);
    setFile(undefined);
  }, [doc, selected]);
  async function action(kind: string) {
    setBusy(true);
    setMsg("");
    try {
      const path = "/admin/documents/" + selected;
      const acl = { public: publicRead, departments, users };
      if (kind === "acl") await api(path + "/acl", "PUT", acl);
      if (kind === "delete") {
        await api(path, "DELETE");
        setSelected("");
      }
      if (kind === "import" || kind === "update") {
        if (!file) throw Error("请选择文件");
        const payload = await uploadData(file);
        if (kind === "update") await api(path, "PUT", payload);
        else {
          const r = await api<{ id: string }>("/admin/documents", "POST", {
            title,
            dept,
            ...acl,
            ...payload,
          });
          setSelected(r.id);
        }
      }
      await refresh();
      changed();
      setMsg("已保存，权限与索引状态已同步。");
      setConfirm(false);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function toggle(items: string[], value: string) {
    return items.includes(value)
      ? items.filter((i) => i !== value)
      : [...items, value];
  }
  return (
    <section className="panel">
      <h2>文档与授权</h2>
      <label>
        选择文档
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">导入新文档</option>
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.id} · {d.title}
            </option>
          ))}
        </select>
      </label>
      {doc ? (
        <p className="meta">
          正文 v{doc.version}　规则 v{doc.acl_version}　所有者 {doc.owner}
          　·　当前账号{doc.reason}
        </p>
      ) : (
        <div className="fields">
          <label>
            文档标题
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            所属部门
            <select value={dept} onChange={(e) => setDept(e.target.value)}>
              {demo.departments.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      <fieldset>
        <legend>正文读取规则</legend>
        <label className="check">
          <input
            type="checkbox"
            checked={publicRead}
            onChange={(e) => setPublic(e.target.checked)}
          />
          全员公开
        </label>
        <h3>部门授权</h3>
        <div className="checks">
          {demo.departments.map((d) => (
            <label className="check" key={d}>
              <input
                type="checkbox"
                checked={departments.includes(d)}
                onChange={() => setDepts(toggle(departments, d))}
              />
              {d}
            </label>
          ))}
        </div>
        <h3>指定用户</h3>
        <div className="checks">
          {demo.accounts.map((a) => (
            <label className="check" key={a.uid}>
              <input
                type="checkbox"
                checked={users.includes(a.uid)}
                onChange={() => setUsers(toggle(users, a.uid))}
              />
              {a.name}（{a.uid}）
            </label>
          ))}
        </div>
      </fieldset>
      {doc && (
        <button disabled={busy} onClick={() => action("acl")}>
          保存授权
        </button>
      )}
      <hr />
      <label>
        接入文件（TXT / Markdown / PDF，最大 2 MiB）
        <input
          key={selected + "-" + doc?.version}
          type="file"
          accept=".txt,.md,.pdf"
          onChange={(e) => setFile(e.target.files?.[0])}
        />
      </label>
      <div className="actions">
        <button
          disabled={busy || !file || (!doc && !title.trim())}
          onClick={() => action(doc ? "update" : "import")}
        >
          {doc ? "更新正文" : "导入文档"}
        </button>
        {doc && (
          <button
            className="danger"
            disabled={busy}
            onClick={() => (confirm ? action("delete") : setConfirm(true))}
          >
            {confirm ? "确认删除文档" : "删除文档"}
          </button>
        )}
      </div>
      <p role="status">{msg}</p>
    </section>
  );
}

type AuditRow = {
  seq: number;
  id: string;
  uid: string;
  time: string;
  event: string;
  decision: string;
  reason: string;
  epoch: number;
  refs: unknown;
  model: string;
  retriever: string;
  ms: number;
};
export function Audit() {
  const [rows, setRows] = useState<AuditRow[]>([]),
    [error, err] = useState("");
  async function load() {
    try {
      setRows(await api("/admin/audit"));
    } catch (e) {
      err((e as Error).message);
    }
  }
  useEffect(() => {
    load();
  }, []);
  return (
    <section className="panel">
      <div className="section-head">
        <h2>访问记录</h2>
        <button className="light" onClick={load}>
          刷新记录
        </button>
      </div>
      <p>{error}</p>
      {rows.map((r) => (
        <details key={r.seq}>
          <summary>
            <b>{r.decision === "allow" ? "允许" : "拒绝"}</b>　{r.uid} /{" "}
            {r.event}　<small>{r.time}</small>
          </summary>
          <p>
            {r.reason} · 授权纪元 {r.epoch} · {r.ms} ms
          </p>
          <code>
            {r.id} · {r.model} · {r.retriever}
          </code>
          <pre>{JSON.stringify(r.refs, null, 2)}</pre>
        </details>
      ))}
    </section>
  );
}

type Metric = { n: number; d: number };
type Case = {
  id: string;
  user: string;
  question: string;
  expected: string;
  actual: string;
  passed: boolean;
};
type Variant = {
  mode: string;
  security: Metric;
  quality: Metric;
  metrics: Record<string, Metric>;
  cases: Case[];
  latency_ms: { p50: number; p95: number };
};
type Report = { variants: Variant[]; split: string; generated_at: string };
export function Evaluation() {
  const [report, set] = useState<Report>(),
    [busy, wait] = useState(false),
    [err, error] = useState("");
  async function run() {
    wait(true);
    error("");
    try {
      set(await api("/admin/evaluate", "POST"));
    } catch (e) {
      error((e as Error).message);
    } finally {
      wait(false);
    }
  }
  return (
    <section className="panel">
      <h2>安全与问答评测</h2>
      <p>在临时合成库中对比普通检索、授权检索与授权缓存。此页运行开发集。</p>
      <button onClick={run} disabled={busy}>
        {busy ? "评测中…" : "运行开发集"}
      </button>
      <p role="status">{err}</p>
      {report && (
        <>
          <p className="meta">完成时间 {report.generated_at}</p>
          {report.variants.map((v) => (
            <article key={v.mode} className="evaluation">
              <h3>{v.mode}</h3>
              <p>
                安全通过{" "}
                <b>
                  {v.security.n}/{v.security.d}
                </b>
                　问答通过{" "}
                <b>
                  {v.quality.n}/{v.quality.d}
                </b>
                　P95 {v.latency_ms.p95} ms
              </p>
              <details>
                <summary>指标明细</summary>
                {Object.entries(v.metrics).map(([k, m]) => (
                  <p key={k}>
                    {k}　{m.n}/{m.d}
                  </p>
                ))}
              </details>
              {v.cases
                .filter((c) => !c.passed)
                .map((c) => (
                  <details className="fail" key={c.id}>
                    <summary>
                      失败案例 · {c.id} · {c.user}
                    </summary>
                    <p>{c.question}</p>
                    <p>预期　{c.expected}</p>
                    <p>实际　{c.actual}</p>
                  </details>
                ))}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
