"""Deterministic metrics and human-readable evidence for paired runs."""
import json

METRICS = {
    "hit_at_5": ("answer", "有权查询 · Hit@5", "前五个过阈值片段中有标注文档"),
    "grounded": ("answer", "有权查询 · 引用与事实", "返回目标引用且回答包含标注事实"),
    "deny_safe": ("deny", "无权查询 · 边界通过", "排序、模型输入、回答和引用均在授权范围内，回答无目标事实"),
    "revoke_flow": ("revoke", "撤权全流程", "冷查、热缓存、撤权后重查、旧引用、历史及审计全部通过"),
    "abstain": ("unknown", "资料不足 · 拒答", "规范拒答文本且引用为空"),
    "passed": ("all", "整体用例通过", "该用例所有断言通过"),
}


def summarize(cases, rows):
    by_id = {r["id"]: r for r in rows}
    result = {}
    for key, (scope, _, _) in METRICS.items():
        selected = [by_id[c["id"]] for c in cases if scope in ("all", c["scenario"])]
        def success(r):
            if key in ("passed", "revoke_flow"):
                return r["status"] == "pass"
            return r["status"] != "error" and r["checks"].get(key, False)
        result[key] = {"passed": sum(success(r) for r in selected), "planned": len(selected),
                       "errors": sum(r["status"] == "error" for r in selected)}
    return result


def description(c):
    target = c.get("doc", "")
    fact = c.get("fact", "")
    return {"answer": f"前五名命中 {target}，回答引用该文档并含 {fact}",
            "deny": f"用户无权查看 {target}，各阶段无越权，回答无 {fact}",
            "revoke": f"先得到 {target} / {fact}，同题命中缓存；撤权后旧内容不可取得",
            "unknown": "资料不足且引用为空"}[c["scenario"]]


def observation(r):
    lines = []
    for phase, v in r["phases"].items():
        if phase in ("old_links", "history"):
            lines.append(f"{phase} = {json.dumps(v, ensure_ascii=False)}")
        else:
            ranks = ", ".join(f"{s['chunk']} ({s['score']:.4f})" for s in v["top5"]) or "空"
            refs = ", ".join(x["id"] for x in v["refs"]) or "空"
            lines.extend([f"{phase} · 前五名 {ranks}；引用 {refs}；缓存 {v['cached']}；纪元 {v['epoch']}",
                          v["answer"].replace("\n", " / ")])
    return lines


def build_report(manifest, rounds):
    cases = manifest["cases"]
    first, second = rounds
    doc = ["# RAG 质量与权限回归对比", "",
           f"数据集 {manifest['dataset']}，评分器 {manifest['scorer']}。"
           f"{len(cases)} 条合成用例，每组配置独立执行两次。", "",
           "| 固定项 | 本轮配置 |", "|---|---|",
           f"| 语料与账号 | {manifest['docs']} 篇，{manifest['accounts']} 个账号；每例从同一种子库复制 |",
           f"| 检索与生成 | {manifest['embedding']}，{manifest['generator']}；前五名留证，第一名送模 |",
           f"| 切块与缓存 | {manifest['chunk_chars']} 字符，重叠 {manifest['overlap_chars']}；开启用户缓存 |",
           f"| 唯一配置差异 | 基线阈值 {first['baseline']['threshold']}，候选阈值 {first['candidate']['threshold']} |",
           f"| 环境 | {manifest['platform']}，Python {manifest['python']}，SQLite {manifest['sqlite']} |", "",
           "配置、全部问题、标签与源文件摘要见 [manifest.json](manifest.json)。"
           "逐阶段证据见[第一轮](round-1.json)和[第二轮](round-2.json)。", ""]
    for i, variants in enumerate(rounds, 1):
        if i == 2 and first == second:
            break
        a, b = variants["baseline"], variants["candidate"]
        doc += [f"## 第 {i} 轮指标", "", "| 指标 | 基线 | 候选 | 差值（通过数） | 成功条件 |",
                "|---|---:|---:|---:|---|"]
        for key, (_, label, rule) in METRICS.items():
            x, y = a["metrics"][key], b["metrics"][key]
            doc.append(f"| {label} | {x['passed']}/{x['planned']} | {y['passed']}/{y['planned']} | "
                       f"{y['passed'] - x['passed']:+d} | {rule} |")
        doc += ["", "分母为该场景全部计划用例。每题计一次；执行错误保留在分母并单列。"
                "无权题允许返回有权材料，此项仅衡量访问边界。Hit@5 使用同一次冷查询的排序，截断阈值后可能少于五条。",
                "", "| 配置 | 通过 | 应用未达预期 | 执行错误 |", "|---|---:|---:|---:|"]
        for name, v in variants.items():
            counts = [sum(r["status"] == k for r in v["cases"]) for k in ("pass", "fail", "error")]
            doc.append(f"| {name} | {counts[0]} | {counts[1]} | {counts[2]} |")
        doc += ["", "### 发生变化的用例", ""]
        changed, evidence_only = [], []
        for x, y in zip(a["cases"], b["cases"], strict=True):
            if x["status"] != y["status"] or x["checks"] != y["checks"]:
                checks = sorted(k for k in x["checks"].keys() | y["checks"].keys()
                                if x["checks"].get(k) != y["checks"].get(k))
                changed.append(f"- {x['id']} · {x['status']} → {y['status']} · {', '.join(checks)}")
            elif x != y:
                evidence_only.append(x["id"])
        doc.extend(changed or ["两组配置的用例结论及断言相同。"])
        doc += ["", "结论相同、逐阶段证据有差异的用例为 " + ("、".join(evidence_only) or "无") + "。", "",
                "### 逐条失败与执行错误", ""]
        failures = 0
        for case, x, y in zip(cases, a["cases"], b["cases"], strict=True):
            if x["status"] == y["status"] == "pass":
                continue
            failures += 1
            doc += [f"#### {case['id']} · {case['user']} · {case['question']}", "",
                    "预期为" + description(case) + "。", ""]
            for name, r in (("基线", x), ("候选", y)):
                broken = ", ".join(k for k, value in r["checks"].items() if not value)
                doc.append(f"- {name} **{r['status']}**" + (f" · 未通过 {broken}" if broken else ""))
                if "error" in r:
                    doc.append(f"  - 执行错误 {r['error']['type']} · {r['error']['detail']}")
                if "application_fault" in r:
                    fault = r["application_fault"]
                    doc.append(f"  - 应用返回 {fault['status_code']} · {fault['detail']}")
                doc.extend("  - " + s for s in observation(r))
            doc.append("")
        if not failures:
            doc.extend(["全部用例通过。", ""])
    doc += ["## 重复运行", "", "逐项比较配置、所有指标和用例证据，包含排序、分数（八位小数）、"
            "回答、引用、实际模型输入、缓存、权限纪元、旧链接、历史及断言。运行时间和随机请求 ID 不参与比较。", ""]
    for name in first:
        differences = [a["id"] for a, b in zip(first[name]["cases"], second[name]["cases"], strict=True) if a != b]
        doc.append(f"- {name} · {len(cases) - len(differences)}/{len(cases)} 条证据一致；"
                   + ("差异见 " + "、".join(differences) if differences else "无逐案差异"))
    doc += ["", "## 解释边界", "", "阈值只决定哪些已有词面匹配可进入结果。定位时先看前五名分数，"
            "再看实际引用和回答；权限问题另查同一用例的模型输入、旧链接状态和历史。"
            "题目包含已有开发题和新增合成题，适合持续回归；原独立保留集另存。"
            "正文评分依赖固定摘录生成器，适用范围为这份合成库和标注事实。", ""]
    return "\n".join(doc)
