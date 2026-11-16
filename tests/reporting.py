"""Optional synthetic evidence export. Allowlist fields so credentials never enter the report."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

EXPECTED = {
    "test_resource_matrix": "引用、下载及可读目录一致，允许返回 200，越权返回 404",
    "test_identity_forgery_and_csrf": "伪造字段 422，管理越权及缺少请求头 403，未认证 401",
    "test_admin_owner_requires_grant_and_versioned_indexes": "仅匹配的个人、部门或公开规则放行；所有片段 ACL 版本同步",
    "test_cache_history_and_audit": "同用户第二次命中，其他用户未命中；实际模型输入和输出来源对应审计，无凭据或正文",
    "test_full_lifecycle": "授权后可读，撤权时清缓存与历史；v1 链接失效，删除后索引与规则清空",
    "test_poisoned_candidate_never_reaches_model": "索引候选复核失败后 404，模型调用数为零",
    "test_fail_closed": "身份、检索或复核服务异常时 503，无模型调用，记录拒绝",
    "test_while_generation_in_flight": "生成中撤权、更新或删除得到 409，退出得到 401，无正文或持久化回答",
    "test_cached_source_is_rechecked_and_history_fails_closed": "模拟未推进纪元的授权漂移，缓存、历史、引用读失败",
    "test_untrusted_text_inert_and_no_tool_access": "上下文仅含已公开的探针，文档指令不能读取 HR 资料或授予管理角色",
    "test_invalid_acl_and_update_are_atomic": "无效输入 422，旧版本和原权限纪元完整保留",
    "test_restart_keeps_revoked_acl": "再次启动后仍保持撤权，旧引用和历史不可读",
    "test_pdf_upload_retrieve_and_download": "PDF 文字被检索、页号正确、下载字节与输入一致",
}


class SyntheticClient(TestClient):
    def __init__(self, app, uid, events):
        super().__init__(app, headers={"X-RAG-Request": "1"})
        self.actor, self.events = uid, events

    def request(self, method, url, **kwargs):
        response = super().request(method, url, **kwargs)
        if self.events is None:
            return response
        body = kwargs.get("json") or {}
        observation = {
            "user": self.actor,
            "request": method + " " + str(url),
            "status": response.status_code,
        }
        if "question" in body:
            observation["question"] = body["question"]
        if str(url).endswith("/acl"):
            observation["requested_rules"] = {
                k: body[k] for k in ("public", "users", "departments") if k in body
            }
        if str(url) == "/api/query" and response.is_success:
            r = response.json()
            observation.update(
                answer=r["answer"],
                chunks=[s["id"] for s in r["refs"]],
                cache=r["cached"],
                epoch=r["epoch"],
            )
        elif response.is_error:
            observation["detail"] = response.json().get("detail")
        self.events.append(observation)
        return response


def pytest_addoption(parser):
    parser.addoption("--case-report", help="Write HTTP security case evidence to a JSON file")


def pytest_configure(config):
    Path("var").mkdir(exist_ok=True)
    config.synthetic_cases = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not item.config.getoption("--case-report") or "rig" not in item.funcargs:
        return
    rig = item.funcargs["rig"]
    item.config.synthetic_cases.append(
        {
            "case": item.name,
            "initial": "Fresh 50-document seed; HR-001 is HR-department, RD-001 is sealed, RD-013 is engineer-only.",
            "expected": EXPECTED[item.originalname],
            "outcome": report.outcome,
            "requests": rig.events,
            "model_inputs": [[r["id"] for r in batch] for batch in rig.probe.calls],
        }
    )


def pytest_sessionfinish(session, exitstatus):
    target = session.config.getoption("--case-report")
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(session.config.synthetic_cases, ensure_ascii=False, indent=2), encoding="utf8"
        )
