"""Measure local HTTP latency separately from in-process stage timings (demo account only)."""

import argparse
import json
import statistics
from pathlib import Path
from time import perf_counter

import httpx


def measure():
    with httpx.Client(
        base_url="http://127.0.0.1:8781/api", headers={"X-RAG-Request": "1"}, trust_env=False
    ) as c:
        c.post("/login", json={"username": "employee", "password": "Orchid-Demo-26"}).raise_for_status()
        samples = []
        for q in [
            "设备报修工单分配给哪里？",
            "会议室预约最多提前几天？",
            "年度安全培训何时完成？",
            "园区班车在哪里发车？",
            "图书借阅期限是多久？",
        ] * 2:
            start = perf_counter()
            response = c.post("/query", json={"question": q})
            elapsed = (perf_counter() - start) * 1000
            response.raise_for_status()
            r = response.json()
            samples.append(
                {
                    "question": q,
                    "cached": r["cached"],
                    "http_ms": round(elapsed, 3),
                    "stages_ms": r["timings_ms"],
                }
            )
        c.post("/logout").raise_for_status()
    ms = [s["http_ms"] for s in samples]
    return {
        "scope": "warm HTTP connection, 10 sequential requests, includes response body transfer, excludes UI and login",
        "p50_ms": round(statistics.median(ms), 3),
        "p95_ms": max(ms),
        "samples": samples,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = measure()
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(result["p50_ms"], result["p95_ms"])
