"""python -m evaluations.run --split dev --out docs/results/dev.json"""

import argparse
import hashlib
import json
import math
import platform
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from rag.adapters import ExtractiveMock, UNKNOWN
from rag.corpus import ACCOUNTS, DEMO_PASSWORD, corpus
from rag.service import Service
from rag.store import Fault, Store

HERE = Path(__file__).parent
ROOT = HERE.parent


class SyntheticUnfiltered(Store):
    """Ablation A. Constructed only for a fresh temporary copy of the public corpus."""

    def retrieve(self, db, user, question):
        q = self.embedding.encode(question)
        candidates = [
            (self.embedding.score(q, row["vector"]), row["id"])
            for row in db.execute("SELECT id,vector FROM chunks")
        ]
        score, cid = max(candidates, default=(0, None))
        return [cid] if score >= self.embedding.threshold else []

    def evidence(self, db, user, ids):
        rows = []
        for cid in ids:
            row = db.execute(
                """SELECT c.id,c.doc,c.version,c.acl_version,c.page,c.start,c.end,c.body,d.title
                FROM chunks c JOIN docs d ON d.id=c.doc WHERE c.id=?""",
                (cid,),
            ).fetchone()
            if not row:
                raise Fault(404, "资料不可用或版本已变更")
            rows.append(dict(row))
        return rows


class Recorder(ExtractiveMock):
    def __init__(self):
        self.seen = []

    def generate(self, question, evidence):
        self.seen.extend(r["id"] for r in evidence)
        return super().generate(question, evidence)


def metric(values):
    return {"n": sum(bool(v) for v in values), "d": len(values)}


def latency(values):
    return {
        "p50": round(statistics.median(values), 3),
        "p95": sorted(values)[math.ceil(len(values) * 0.95) - 1],
    }


def allowed(uid, doc):
    dept = next(a[3] for a in ACCOUNTS if a[0] == uid)
    return doc["public"] or uid in doc["users"] or dept in doc["departments"]


def run_variant(folder, mode, questions):
    store = (SyntheticUnfiltered if mode == "A" else Store)(folder / (mode + ".db"))
    store.initialize()
    spy = Recorder()
    service = Service(store, spy, cache=mode == "C")
    tokens = {a[0]: store.login(a[0], DEMO_PASSWORD) for a in ACCOUNTS}
    fixtures = {r["id"]: r for r in corpus()}
    cases, times, stages = [], [], {}
    stats = {
        k: []
        for k in (
            "hit_at_1",
            "answer_with_reference_fact",
            "reference_correct_and_allowed",
            "abstention",
            "zh",
            "en",
        )
    }
    security, quality = [], []

    def query(uid, q):
        spy.seen.clear()
        return service.ask(tokens[uid], q)

    for case, uid, lang, q, doc, fact in questions:
        res = query(uid, q)
        refs = res["refs"]
        actual = [r["doc"] for r in refs]
        hit = actual == [doc] if doc else not actual
        good = hit and (
            fact.casefold() in res["answer"].casefold() if fact else res["answer"] == UNKNOWN
        )
        permitted = all(allowed(uid, fixtures[r["doc"]]) for r in refs)
        if doc:
            stats["hit_at_1"].append(hit)
            stats["answer_with_reference_fact"].append(good and permitted)
        else:
            stats["abstention"].append(good)
        for r in refs:
            body = fixtures[r["doc"]]["raw"].decode()[r["start"] : r["end"]]
            stats["reference_correct_and_allowed"].append(
                r["doc"] == doc and permitted and bool(fact) and fact.casefold() in body.casefold()
            )
        stats[lang].append(good and permitted)
        quality.append(good and permitted)
        times.append(res["ms"])
        for stage, value in res["timings_ms"].items():
            stages.setdefault(stage, []).append(value)
        cases.append(
            {
                "id": case,
                "suite": "quality",
                "user": uid,
                "initial": "seed manifest",
                "question": q,
                "expected": f"{doc} / {fact}" if doc else UNKNOWN,
                "actual": res["answer"],
                "passed": quality[-1],
                "refs": actual,
                "context": list(spy.seen),
                "ms": res["ms"],
                "timings_ms": res["timings_ms"],
            }
        )

    def check(case, uid, q, initial, expected, actual, passed, **extra):
        security.append(bool(passed))
        cases.append(
            dict(
                id=case,
                suite="security",
                user=uid,
                question=q,
                initial=initial,
                expected=expected,
                actual=actual,
                passed=bool(passed),
                **extra,
            )
        )

    def check_query(case, uid, q, doc, marker, should_read, initial, cache_expected=None):
        res = query(uid, q)
        refs = [r["id"] for r in res["refs"]]
        ctx = list(spy.seen)
        in_refs = any(s.startswith(doc + ".") for s in refs)
        in_ctx = any(s.startswith(doc + ".") for s in ctx)
        ok = (
            in_refs == should_read
            and (marker in res["answer"]) == should_read
            and in_ctx == (should_read and not res["cached"])
        )
        if cache_expected is not None:
            ok = ok and res["cached"] == cache_expected
        with store.transaction() as db:
            logged = json.loads(
                db.execute("SELECT refs FROM audit WHERE id=?", (res["id"],)).fetchone()[0]
            )
        ok = ok and logged["context"] == ctx and [r["id"] for r in logged["sources"]] == refs
        check(
            case,
            uid,
            q,
            initial,
            "命中授权来源" if should_read else "正文、引用、模型上下文均无目标资料",
            res["answer"],
            ok,
            refs=refs,
            context=ctx,
            cached=res["cached"],
        )
        return res

    salary = "薪酬复核的内部校验码是什么？"
    project = "星桥发布的验收口令是什么？"
    check_query("S01", "hr", salary, "HR-001", "HR-ORCHID-72", True, "人事部授权")
    check_query("S02", "employee", salary, "HR-001", "HR-ORCHID-72", False, "相同问题已由 HR 查询")
    check_query("S03", "admin", salary, "HR-001", "HR-ORCHID-72", False, "仅管理权限")
    check_query(
        "S04", "peer", "蓝图归档的盒号是什么？", "RD-013", "QUARTZ-39", False, "同部门另一用户获授权"
    )

    def change(action, **data):
        with store.transaction(True) as db:
            store.change(db, "RD-001", action, **data)

    def reference(case, cid, initial):
        try:
            with store.transaction() as db:
                u = store.identity(db, tokens["engineer"])
                rows = store.evidence(db, u, [cid])
            actual = rows[0]["body"]
            ok = False
        except Fault as e:
            actual, ok = str(e.status), e.status == 404
        check(case, "engineer", cid, initial, "404", actual, ok)

    change("acl", public=False, departments=[], users=["engineer"])
    r = check_query("S05", "engineer", project, "RD-001", "RD-CEDAR-41", True, "个人授权")
    old = r["refs"][0]["id"]
    check_query(
        "S06", "engineer", project, "RD-001", "RD-CEDAR-41", True, "相同用户重复查询", mode == "C"
    )
    change("acl", public=False, departments=[], users=[])
    check_query("S07", "engineer", project, "RD-001", "RD-CEDAR-41", False, "已撤销上轮授权", False)
    reference("S08", old, "撤权后的原链接")
    with store.transaction() as db:
        hist = service.history(db, store.identity(db, tokens["engineer"]))
    safe = "RD-CEDAR-41" not in json.dumps(hist)
    check(
        "S09",
        "engineer",
        "GET history",
        "撤权后再查询",
        "历史无旧正文",
        str([r["id"] for r in hist]),
        safe,
    )
    change("acl", public=False, departments=[], users=["engineer"])
    change("update", filename="release.txt", raw="星桥发布的验收口令是 RD-NEW-52。".encode())
    check_query("S10", "engineer", project, "RD-001", "RD-NEW-52", True, "同一文档已更新到 v2", False)
    reference("S11", old, "旧版本已失效")
    change("delete")
    check_query("S12", "engineer", project, "RD-001", "RD-NEW-52", False, "文档已删除", False)
    reference("S13", "RD-001.v2.1", "删除后的原链接")
    return {
        "mode": mode,
        "security": metric(security),
        "quality": metric(quality),
        "metrics": {k: metric(v) for k, v in stats.items()},
        "latency_ms": latency(times),
        "stage_ms": {k: latency(v) for k, v in stages.items()},
        "cases": cases,
    }


def run_suite(split="dev"):
    if split not in {"dev", "holdout"}:
        raise ValueError("未知数据集")
    raw = (HERE / (split + ".json")).read_bytes()
    scratch = ROOT / "var" / "evaluations"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=scratch) as folder:
        variants = [run_variant(Path(folder), m, json.loads(raw)) for m in "ABC"]
    return {
        "split": split,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "corpus_source_sha256": hashlib.sha256((ROOT / "rag" / "corpus.py").read_bytes()).hexdigest(),
        "config": {
            "generator": "extractive-mock-v1",
            "embedding": "lexical-hash-65536-v1",
            "threshold": 0.18,
            "top_k": 1,
            "chunk": 420,
            "overlap": 60,
        },
        "variants": variants,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_suite(args.split)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    for v in report["variants"]:
        print(
            v["mode"], "security", v["security"], "quality", v["quality"], "latency_ms", v["latency_ms"]
        )
