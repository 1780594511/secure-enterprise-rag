import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .adapters import LocalEmbedding
from .corpus import ACCOUNTS, DEPARTMENTS, DEMO_PASSWORD, corpus
from .ingest import parse, split


class Fault(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verifier(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)


def identifier():
    return uuid.uuid4().hex


# All three operands come from authenticated server state or authoritative ACL tables.
ALLOWED = """(d.public=1 OR EXISTS (SELECT 1 FROM grants g WHERE g.doc=d.id AND
    ((g.kind='dept' AND g.target=:dept) OR (g.kind='user' AND g.target=:uid))))"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.embedding = LocalEmbedding()

    @contextmanager
    def transaction(self, write=False):
        db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction(True) as db:
            for sql in Path(__file__).with_name("schema.sql").read_text("utf8").split(";"):
                if sql.strip():
                    db.execute(sql)
            if db.execute("SELECT 1 FROM state").fetchone():
                return
            db.execute("INSERT INTO state VALUES(1,1)")
            for uid, name, role, dept in ACCOUNTS:
                salt = secrets.token_bytes(16)
                db.execute(
                    "INSERT INTO users VALUES(?,?,?,?,?,?)",
                    (uid, name, role, dept, salt, verifier(DEMO_PASSWORD, salt)),
                )
            for doc in corpus():
                self.insert(db, **doc)

    def login(self, uid, password):
        with self.transaction(True) as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            candidate = verifier(password, row["salt"] if row else bytes(16))
            if not row or not hmac.compare_digest(candidate, row["verifier"]):
                raise Fault(401, "账号或口令有误")
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?)", (digest(token), uid, int(time.time()) + 28800)
            )
            return token

    def identity(self, db, token):
        row = db.execute(
            """SELECT u.id AS uid,u.name,u.role,u.dept FROM users u JOIN sessions s ON s.uid=u.id
            WHERE s.digest=? AND s.expires>?""",
            (digest(token), time.time()),
        ).fetchone()
        if not row:
            raise Fault(401, "请重新登录")
        return dict(row)

    @staticmethod
    def epoch(db):
        return db.execute("SELECT epoch FROM state WHERE id=1").fetchone()[0]

    @staticmethod
    def invalidate(db):
        db.execute("UPDATE state SET epoch=epoch+1 WHERE id=1")
        db.execute("DELETE FROM answers")

    def set_grants(self, db, doc, departments, users):
        known = {r[0] for r in db.execute("SELECT id FROM users")}
        if not set(users) <= known or not set(departments) <= DEPARTMENTS:
            raise Fault(422, "未知的用户或部门")
        db.execute("DELETE FROM grants WHERE doc=?", (doc,))
        db.executemany(
            "INSERT INTO grants VALUES(?,?,?)",
            [
                (doc, kind, value)
                for kind, values in [("dept", departments), ("user", users)]
                for value in set(values)
            ],
        )

    def index(self, db, doc, version, acl_version, title, pages):
        db.execute("DELETE FROM chunks WHERE doc=?", (doc,))
        for i, (page, start, end, body) in enumerate(split(pages)):
            vector = self.embedding.encode(title + " " + body)
            db.execute(
                "INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    f"{doc}.v{version}.{i + 1}",
                    doc,
                    version,
                    acl_version,
                    page,
                    start,
                    end,
                    body,
                    json.dumps(vector),
                ),
            )

    def insert(self, db, id, title, dept, owner, public, departments, users, filename, raw):
        pages = parse(filename, raw)
        if dept not in DEPARTMENTS:
            raise Fault(422, "未知的所属部门")
        db.execute(
            "INSERT INTO docs VALUES(?,?,?,?,1,1,?,?,?)",
            (id, title, dept, owner, int(public), filename, raw),
        )
        self.set_grants(db, id, departments, users)
        self.index(db, id, 1, 1, title, pages)

    def change(self, db, doc, action, **data):
        row = db.execute("SELECT title,version,acl_version FROM docs WHERE id=?", (doc,)).fetchone()
        if not row:
            raise Fault(404, "资料不可用")
        if action == "acl":
            self.set_grants(db, doc, data["departments"], data["users"])
            db.execute(
                "UPDATE docs SET public=?,acl_version=acl_version+1 WHERE id=?",
                (int(data["public"]), doc),
            )
            db.execute("UPDATE chunks SET acl_version=? WHERE doc=?", (row["acl_version"] + 1, doc))
        elif action == "update":
            pages = parse(data["filename"], data["raw"])
            db.execute(
                "UPDATE docs SET filename=?,original=?,version=version+1 WHERE id=?",
                (data["filename"], data["raw"], doc),
            )
            self.index(db, doc, row["version"] + 1, row["acl_version"], row["title"], pages)
        elif action == "delete":
            db.execute("DELETE FROM docs WHERE id=?", (doc,))
        else:
            raise ValueError("未知的操作")
        self.invalidate(db)

    def list_docs(self, db, user, management=False):
        if management and user["role"] != "管理员":
            raise Fault(403, "需要管理权限")
        sql = "SELECT id,title,dept,owner,version,acl_version,public FROM docs d"
        if not management:
            sql += " WHERE " + ALLOWED
        result = []
        for row in db.execute(sql + " ORDER BY id", user):
            item = dict(row)
            grants = db.execute(
                "SELECT kind,target FROM grants WHERE doc=? ORDER BY target", (row["id"],)
            ).fetchall()
            reasons = (["全员公开"] if item["public"] else []) + [
                "部门授权" if kind == "dept" else "指定用户"
                for kind, target in grants
                if (kind, target) in {("dept", user["dept"]), ("user", user["uid"])}
            ]
            item["reason"] = "、".join(reasons) or "无正文权限"
            if management:
                item["departments"] = [target for kind, target in grants if kind == "dept"]
                item["users"] = [target for kind, target in grants if kind == "user"]
            result.append(item)
        return result

    def retrieve(self, db, user, question):
        vector = self.embedding.encode(question)
        rows = db.execute(
            """SELECT c.id,c.vector FROM chunks c JOIN docs d ON c.doc=d.id
            WHERE c.version=d.version AND c.acl_version=d.acl_version AND """
            + ALLOWED
            + " ORDER BY c.id",
            user,
        )
        scored = [(self.embedding.score(vector, r["vector"]), r["id"]) for r in rows]
        if not scored:
            return []
        score, chunk_id = max(scored)
        return [chunk_id] if score >= self.embedding.threshold else []

    def evidence(self, db, user, ids):
        refs = []
        for cid in ids:
            row = db.execute(
                """SELECT c.id,c.doc,c.version,c.acl_version,c.page,c.start,c.end,c.body,d.title
                FROM chunks c JOIN docs d ON d.id=c.doc WHERE c.id=:cid AND c.version=d.version
                AND c.acl_version=d.acl_version AND """
                + ALLOWED,
                {**user, "cid": cid},
            ).fetchone()
            if not row:
                raise Fault(404, "资料不可用或版本已变更")
            refs.append(dict(row))
        return refs
