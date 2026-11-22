"""Offline paired regression against the production query service and synthetic seed."""
import argparse
import hashlib
import json
import platform
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from rag.adapters import ExtractiveMock, LocalEmbedding, UNKNOWN
from rag.corpus import ACCOUNTS, DEMO_PASSWORD, corpus
from rag.ingest import split
from rag.service import Service
from rag.store import Fault, Store

from .regression_report import build_report, summarize
from .run import allowed

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evaluations/regression-v1.json"
THRESHOLDS = {"baseline": 0.18, "candidate": 0.12}
SCORER = "extractive-acl-v1"
DOCS = {doc["id"]: doc for doc in corpus()}
# Independent expected text comes from the public manifest, never the live ACL query.
CHUNKS = {
    f"{doc['id']}.v1.{i}": (doc["id"], body)
    for doc in DOCS.values()
    for i, (_, _, _, body) in enumerate(split([doc["raw"].decode()]), 1)
}


class ObservedStore(Store):
    """Observe five from the same ranking pass; Service still consumes its requested Top-1."""
    def ranked(self, db, user, question, limit):
        ranked = super().ranked(db, user, question, max(5, limit))
        self.top5 = [{"chunk": cid, "score": round(score, 8)} for score, cid in ranked[:5]]
        return ranked[:limit]


class ObservedMock(ExtractiveMock):
    def generate(self, question, evidence):
        self.inputs.extend((r["id"], r["body"]) for r in evidence)
        return super().generate(question, evidence)


def load_fixture():
    data = json.loads(FIXTURE.read_text("utf8"))
    seen = set()
    for c in data["cases"]:
        uid, kind = c["user"], c["scenario"]
        if (c["id"] in seen or uid not in {a[0] for a in ACCOUNTS}
                or not c["question"].strip() or kind not in {"answer", "deny", "unknown", "revoke"}):
            raise ValueError(f"无效用例 {c['id']}")
        seen.add(c["id"])
        if kind == "unknown":
            continue
        doc = DOCS[c["doc"]]
        if not c["fact"] or c["fact"].casefold() not in doc["raw"].decode().casefold():
            raise ValueError(f"参考事实与语料不符 {c['id']}")
        if kind != "revoke" and allowed(uid, doc) != (kind == "answer"):
            raise ValueError(f"标注与初始授权不符 {c['id']}")
    return data


def safe_output(answer, refs, readable):
    """The fixed mock returns one full source chunk or the canonical abstention."""
    bodies = []
    for ref in refs:
        source = CHUNKS.get(ref["id"])
        if not source or source[0] != ref["doc"] or source[0] not in readable:
            return False
        bodies.append(source[1])
    return answer == UNKNOWN or answer in bodies


def query(service, token, case, readable):
    store, probe = service.store, service.generator
    store.top5, probe.inputs = [], []
    result = service.ask(token, case["question"])
    refs = [{"id": r["id"], "doc": r["doc"]} for r in result["refs"]]
    ids = [r["id"] for r in refs]
    context = [cid for cid, _ in probe.inputs]
    with store.transaction() as db:
        row = db.execute("SELECT refs FROM audit WHERE id=? AND uid=? AND event='query'",
                         (result["id"], case["user"])).fetchone()
    trace = json.loads(row[0]) if row else {}
    audit_ok = (trace.get("context") == context and trace.get("sources") == result["refs"]
                and trace.get("candidates") == ids)
    ranked_ids = [r["chunk"] for r in store.top5]
    if not result["cached"]:
        audit_ok = audit_ok and ranked_ids[:1] == ids
    safe = (safe_output(result["answer"], refs, readable)
            and all(cid in CHUNKS and CHUNKS[cid][0] in readable for cid in ranked_ids)
            and all(cid in CHUNKS and CHUNKS[cid][0] in readable and body == CHUNKS[cid][1]
                    for cid, body in probe.inputs))
    return dict(answer=result["answer"], refs=refs, top5=store.top5, context=context,
                cached=result["cached"], epoch=result["epoch"], authorized=safe, audit_ok=audit_ok)


def has_answer(obs, case):
    return (case["doc"] in [r["doc"] for r in obs["refs"]]
            and case["fact"].casefold() in obs["answer"].casefold())


def change_grants(service, admin, doc, users):
    def update(db, actor):
        service.store.change(db, doc, "acl", public=False, departments=[], users=users)
    service.guarded(admin, "acl", update, admin=True, resource={"doc": doc})


def run_case(service, tokens, case, phases, checks):
    uid, kind = case["user"], case["scenario"]
    token, doc = tokens[uid], case.get("doc")
    readable = {d for d, row in DOCS.items() if allowed(uid, row)}

    def ask(phase):
        obs = phases[phase] = query(service, token, case, readable)
        checks[phase + "_acl"] = obs["authorized"]
        checks[phase + "_audit"] = obs["audit_ok"]
        return obs

    if kind != "revoke":
        obs = ask("query")
        checks["cold"] = not obs["cached"]
        if kind == "answer":
            checks["hit_at_5"] = any(CHUNKS.get(r["chunk"], (None,))[0] == doc for r in obs["top5"])
            checks["grounded"] = has_answer(obs, case)
        elif kind == "unknown":
            checks["abstain"] = obs["answer"] == UNKNOWN and not obs["refs"]
        else:
            checks["deny_safe"] = obs["authorized"] and case["fact"].casefold() not in obs["answer"].casefold()
        return

    change_grants(service, tokens["admin"], doc, [uid])
    readable.add(doc)
    cold, warm = ask("granted"), ask("warm")
    checks["granted_read"] = has_answer(cold, case) and not cold["cached"]
    checks["warm_hit"] = (warm["cached"] and not warm["context"] and has_answer(warm, case)
                          and cold["refs"] == warm["refs"] and cold["epoch"] == warm["epoch"])
    change_grants(service, tokens["admin"], doc, [])
    readable.remove(doc)
    after = ask("revoked")
    checks["revoked_safe"] = (after["authorized"] and not after["cached"] and after["epoch"] > warm["epoch"]
                              and case["fact"].casefold() not in after["answer"].casefold())
    statuses = {}
    for r in cold["refs"]:
        if r["doc"] != doc:
            continue
        try:
            service.guarded(token, "reference", lambda db, u: service.store.evidence(db, u, [r["id"]])[0])
            statuses[r["id"]] = 200
        except Fault as exc:
            if exc.status >= 500:
                raise
            statuses[r["id"]] = exc.status
    phases["old_links"] = statuses
    checks["old_links_404"] = bool(statuses) and all(v == 404 for v in statuses.values())
    history = service.guarded(token, "history", service.history)
    phases["history"] = [
        {"answer": h["answer"], "refs": [{"id": r["id"], "doc": r["doc"]} for r in h["refs"]]}
        for h in history
    ]
    checks["history_safe"] = all(safe_output(h["answer"], h["refs"], readable)
                                 and case["fact"].casefold() not in h["answer"].casefold() for h in history)


def failure(exc):
    return {"type": type(exc).__name__, "detail": str(exc), "status_code": getattr(exc, "status", None)}


def run_config(folder, threshold, cases):
    seed = Store(folder / "seed.db")
    setup_error = None
    try:
        seed.initialize()
        tokens = {a[0]: seed.login(a[0], DEMO_PASSWORD) for a in ACCOUNTS}
    except Exception as exc:
        setup_error = failure(exc)
    rows = []
    for case in cases:
        row = {"id": case["id"], "phases": {}, "checks": {}}
        if setup_error:
            row.update(status="error", error=setup_error)
        else:
            try:
                # Seed connections are closed. Case-local copies isolate caches, ACL epochs and history.
                path = folder / "case.db"
                shutil.copyfile(seed.path, path)
                store = ObservedStore(path)
                store.embedding.threshold = threshold
                service = Service(store, ObservedMock())
                run_case(service, tokens, case, row["phases"], row["checks"])
                row["status"] = "pass" if all(row["checks"].values()) else "fail"
            except Fault as exc:
                row["checks"]["application_response"] = False
                row.update(status="fail", application_fault=failure(exc))
            except Exception as exc:
                row.update(status="error", error=failure(exc))
        rows.append(row)
    return rows


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint():
    files = [*sorted((ROOT / "rag").glob("*.py")), ROOT / "rag/schema.sql", ROOT / "requirements.lock",
             Path(__file__), ROOT / "evaluations/regression_report.py", ROOT / "evaluations/run.py", FIXTURE]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in files}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def run(out):
    fixture = load_fixture()
    out.mkdir(parents=True, exist_ok=False)
    scratch = ROOT / "var/evaluations"
    scratch.mkdir(parents=True, exist_ok=True)
    manifest = {"dataset": fixture["version"], "scorer": SCORER, "files_sha256": fingerprint(),
                "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                "platform": platform.platform(), "docs": len(DOCS), "accounts": len(ACCOUNTS),
                "embedding": LocalEmbedding.name,
                "generator": ExtractiveMock.name, "chunk_chars": 420, "overlap_chars": 60,
                "cache": True, "ranking_depth": 5, "generation_depth": 1, "thresholds": THRESHOLDS,
                "expectations": fixture["expectations"], "cases": fixture["cases"]}
    write_json(out / "manifest.json", manifest)
    rounds = []
    for index in (1, 2):
        variants = {}
        for name, threshold in THRESHOLDS.items():
            with TemporaryDirectory(dir=scratch) as tmp:
                rows = run_config(Path(tmp), threshold, fixture["cases"])
            variants[name] = {"threshold": threshold, "cases": rows, "metrics": summarize(fixture["cases"], rows)}
        record = {"round": index, "finished_utc": datetime.now(timezone.utc).isoformat(),
                  "manifest_sha256": sha(out / "manifest.json"), "variants": variants}
        write_json(out / f"round-{index}.json", record)
        rounds.append(variants)
    report = build_report(manifest, rounds)
    (out / "comparison.md").write_text(report, encoding="utf8")
    print(str(out / "comparison.md"))
    if any(r["status"] == "error" for variants in rounds for variant in variants.values() for r in variant["cases"]):
        return 2
    return 0 if rounds[0] == rounds[1] else 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="固定语料和评分规则，运行两轮基线/候选对照")
    parser.add_argument("--out", type=Path, help="新建的结果目录，默认按 UTC 时间保存")
    args = parser.parse_args()
    destination = args.out or ROOT / "var/regression" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        sys.exit(run(destination))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"{type(exc).__name__}: {exc}\n")
