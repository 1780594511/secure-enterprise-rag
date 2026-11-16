import json
import sqlite3
import time

from .adapters import UNKNOWN
from .ingest import InvalidFile
from .store import Fault, identifier


def metadata(rows):
    return [{k: v for k, v in row.items() if k != "body"} for row in rows]


class Service:
    def __init__(self, store, generator, cache=True):
        self.store, self.generator, self.cache = store, generator, cache

    @property
    def config(self):
        return self.generator.name + "|" + self.store.embedding.name + "|top1"

    def log(self, db, request, uid, event, decision, reason, refs, started):
        db.execute(
            """INSERT INTO audit(id,uid,event,decision,reason,epoch,refs,model,retriever,ms)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                request,
                uid,
                event,
                decision,
                reason,
                self.store.epoch(db),
                json.dumps(refs, ensure_ascii=False),
                self.generator.name,
                self.store.embedding.name,
                round((time.perf_counter() - started) * 1000, 2),
            ),
        )

    def denied(self, request, uid, event, reason, refs, started):
        try:
            with self.store.transaction(True) as db:
                self.log(db, request, uid, event, "deny", reason, refs, started)
        except sqlite3.Error:
            pass  # An unavailable audit database cannot be used to authorize a response.

    def ask(self, token, question):
        s = self.store
        question = question.strip()
        if not question:
            raise Fault(422, "问题不能为空")
        started = time.perf_counter()
        rid, uid = identifier(), "anonymous"
        trace = {"candidates": [], "context": [], "sources": []}
        try:
            with s.transaction() as db:
                user = s.identity(db, token)
                uid, epoch = user["uid"], s.epoch(db)
                hit = (
                    db.execute(
                        "SELECT * FROM answers WHERE uid=? AND epoch=? AND q=? AND config=? ORDER BY rowid DESC LIMIT 1",
                        (uid, epoch, question, self.config),
                    ).fetchone()
                    if self.cache
                    else None
                )
                ids = json.loads(hit["refs"]) if hit else s.retrieve(db, user, question)
                trace["candidates"] = ids
            retrieved = time.perf_counter()
            # A fresh transaction rehydrates text from the authority, never from vector results.
            with s.transaction() as db:
                user = s.identity(db, token)
                if s.epoch(db) != epoch:
                    raise Fault(409, "权限或资料已变更，请重新提问")
                evidence = s.evidence(db, user, ids)
            authorized = time.perf_counter()
            if hit:
                answer = hit["body"]
            elif evidence:
                trace["context"] = ids
                answer = self.generator.generate(question, evidence)
            else:
                answer = UNKNOWN
            generated = time.perf_counter()
            with s.transaction(True) as db:
                user = s.identity(db, token)
                if s.epoch(db) != epoch:
                    raise Fault(409, "权限或资料已变更，请重新提问")
                refs = metadata(s.evidence(db, user, ids))
                trace["sources"] = refs
                db.execute(
                    "INSERT INTO answers VALUES(?,?,?,?,?,?,?,?)",
                    (rid, uid, epoch, question, answer, json.dumps(ids), self.config, int(time.time())),
                )
                self.log(
                    db,
                    rid,
                    uid,
                    "query",
                    "allow",
                    "cache" if hit else ("authorized" if ids else "insufficient"),
                    trace,
                    started,
                )
                final = time.perf_counter()
                times = [started, retrieved, authorized, generated, final]
                timings = {
                    k: round((b - a) * 1000, 3)
                    for k, a, b in zip(
                        ["retrieval", "authorization", "generation", "final_check"], times, times[1:]
                    )
                }
                return {
                    "id": rid,
                    "answer": answer,
                    "refs": refs,
                    "cached": bool(hit),
                    "epoch": epoch,
                    "model": self.generator.name,
                    "timings_ms": timings,
                    "ms": round((final - started) * 1000, 3),
                }
        except Exception as exc:
            trace["sources"] = []
            message = exc.message if isinstance(exc, Fault) else "授权、检索或生成服务不可用"
            self.denied(rid, uid, "query", message, trace, started)
            if isinstance(exc, Fault):
                raise
            raise Fault(503, message) from None

    def guarded(self, token, event, operation, admin=False, resource=None):
        started, rid, uid = time.perf_counter(), identifier(), "anonymous"
        try:
            with self.store.transaction(True) as db:
                user = self.store.identity(db, token)
                uid = user["uid"]
                if admin and user["role"] != "管理员":
                    raise Fault(403, "需要管理权限")
                result = operation(db, user)
                self.log(
                    db,
                    rid,
                    uid,
                    event,
                    "allow",
                    "管理角色" if admin else "当前身份及访问规则",
                    resource or {},
                    started,
                )
                return result
        except Exception as exc:
            message = (
                exc.message
                if isinstance(exc, Fault)
                else (
                    str(exc) if isinstance(exc, InvalidFile) else "服务不可用"
                )
            )
            self.denied(rid, uid, event, message, resource or {}, started)
            if isinstance(exc, Fault):
                raise
            raise Fault(422 if isinstance(exc, InvalidFile) else 503, message) from None

    def history(self, db, user):
        rows = db.execute(
            "SELECT * FROM answers WHERE uid=? AND epoch=? ORDER BY rowid DESC LIMIT 30",
            (user["uid"], self.store.epoch(db)),
        )
        return [
            {
                "id": r["id"],
                "question": r["q"],
                "answer": r["body"],
                "refs": metadata(self.store.evidence(db, user, json.loads(r["refs"]))),
            }
            for r in rows
        ]
