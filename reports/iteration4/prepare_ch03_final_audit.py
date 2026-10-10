"""Read-only capture of intermediate CH03 evidence, never a final grade or API test."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT / "workspace/iteration2-live"
RUN_ID = "a45be503af594ce8aae0bb1e4c30184b"
PLAN_HASH = "fbd172c8df0c12fca976e9067b04afe5210016559e210ca8dd0c3e7d37f3f1f7"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_candidate(section_id: str) -> dict:
    state_path = WORKSPACE / "runs" / RUN_ID / "local-repair" / f"{section_id}.json"
    for _ in range(3):
        state_raw = state_path.read_bytes()
        state = json.loads(state_raw)
        assert state["identity"]["plan_hash"] == PLAN_HASH
        assert state["identity"]["section_id"] == section_id
        path = (WORKSPACE / state["candidate_key"]).resolve()
        assert path.is_relative_to(WORKSPACE.resolve())
        candidate_raw = path.read_bytes()
        assert sha(candidate_raw) == state["candidate_hash"]
        dependencies = []
        for dependency in state.get("evidence_dependencies", []):
            source = (WORKSPACE / dependency["key"]).resolve()
            assert source.is_relative_to(WORKSPACE.resolve())
            actual = sha(source.read_bytes())
            assert actual == dependency["hash"]
            dependencies.append({"path": str(source), "sha256": actual})
        if state_path.read_bytes() != state_raw:
            continue
        candidate = json.loads(candidate_raw)
        assert candidate["section_id"] == section_id
        return {
            "section_id": section_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "state_path": str(state_path),
            "state_sha256": sha(state_raw),
            "candidate_path": str(path),
            "candidate_sha256": sha(candidate_raw),
            "phase_at_capture": state["phase"],
            "identity": state["identity"],
            "dependencies": dependencies,
            "unit_counts": dict(Counter(unit["kind"] for unit in candidate["units"])),
            "state_raw": state_raw,
            "candidate_raw": candidate_raw,
        }
    raise RuntimeError(f"Concurrent changes prevented stable capture: {section_id}")


def main() -> None:
    baseline_path = PROJECT / "reports/iteration2/lecture_semantic_baselines.json"
    baseline_raw = baseline_path.read_bytes()
    baseline = json.loads(baseline_raw)
    chapter = next(c for c in baseline["chapters"] if c["id"] == "CH03")
    captures = [read_candidate(f"S{n:02}") for n in range(1, 6)]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = PROJECT / "reports/iteration4" / f"ch03-audit-preparation-{stamp}"
    output.mkdir(exist_ok=False)
    for capture in captures:
        sid = capture["section_id"]
        for kind in ("state", "candidate"):
            local = output / f"{sid}.{kind}.intermediate.json"
            local.write_bytes(capture.pop(f"{kind}_raw"))
            capture[f"snapshot_{kind}"] = local.name
    required = []
    optional = []
    for original in chapter["checklist"]:
        row = {k: v for k, v in original.items() if k != "evaluation"}
        row["evaluation"] = {
            "status": "PENDING_FINAL" if row["scope"] == "REQUIRED" else "NOT_REQUIRED",
            "reason": "Final artifacts have not been frozen for this audit.",
            "generated_evidence": [],
            "required_evidence_fields": ["unit_id", "tex_path", "tex_sha256", "tex_line", "pdf_path", "pdf_sha256", "pdf_physical_page", "reasoning"],
        }
        (required if row["scope"] == "REQUIRED" else optional).append(row)
    assert len(required) == 22 and len(optional) == 3
    common = [{"id": x["id"], "check": x["check"], "status": "PENDING_FINAL", "evidence": []} for x in baseline["teaching_review_checklist"]]
    assert len(common) == 8
    findings = [
        {"id": "I01", "classification": "COVERAGE_GAP_INTERMEDIATE", "sections": ["S03"], "units": ["S03.U03", "S03.U04"], "baseline_ids": ["CH03-T04", "CH03-P03"], "observation": "The entire captured S03 gives sin(x)/x and (exp(x)-1)/x, but no classical (1+x)^(1/x) -> e or discrete positive-base generalization. The exp difference-quotient statement itself is correct; its independent foundational inequality is explicitly declared.", "next_check": "Read the full final chapter for the missing forms and legitimate prerequisites; do not reject correct alternative proofs."},
        {"id": "I02", "classification": "COVERAGE_GAP_INTERMEDIATE", "sections": ["S03"], "units": ["S03.U02"], "baseline_ids": ["CH03-D04"], "observation": "Equivalent infinitesimals are explicitly defined correctly, but the captured entire S03 does not define same order / higher order.", "next_check": "Check whole final chapter with one consistent nonzero comparison constant convention."},
        {"id": "I03", "classification": "TRAINING_GAP_INTERMEDIATE", "sections": ["S03"], "units": ["S03.U06", "S03.U07", "S03.U08", "S03.U09", "S03.U10"], "baseline_ids": ["CH03-T05", "G04"], "observation": "Addition/subtraction replacement is correctly warned against, but no actual cancellation example or counterexample is worked in captured S03.", "next_check": "Require a concrete valid counterexample or error analysis, not a specific gold expression."},
        {"id": "I04", "classification": "TRAINING_GAP_INTERMEDIATE", "sections": ["S02"], "units": ["S02.U01", "S02.U04", "S02.U08", "S02.U10", "S02.U12"], "baseline_ids": ["CH03-T03", "G02", "G03"], "observation": "Squeeze is stated twice and proved, but section examples/exercise use algebra rather than squeeze. The following S03 proof does use squeeze; no actual squeeze practice problem is present in the captured chapter.", "next_check": "Judge final approved learning objective and exercises, not mere word counts."},
        {"id": "I05", "classification": "APPLICATION_CLARITY_INTERMEDIATE", "sections": ["S05"], "units": ["S05.U13", "S05.U14", "S05.U18", "S05.U22"], "baseline_ids": ["CH03-A01", "G07"], "observation": "Price and supply/demand symbols, domains, nonnegativity and continuity are explained. Units of price/quantity are not stated. Existence, strict-monotonicity uniqueness, and the continuous piecewise-linear multiple-equilibrium counterexample are mathematically correct.", "next_check": "Retain correct uniqueness reasoning; inspect final units and model boundaries."},
    ]
    report = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "CH03 final audit preparation with explicitly intermediate evidence",
        "run_id": RUN_ID, "approved_plan_hash_from_parent": PLAN_HASH,
        "capture_policy": "Each mutable state was stable across candidate/dependency SHA verification; sections were read sequentially while the job was active, not as an atomic final chapter snapshot.",
        "baseline": {"path": str(baseline_path), "sha256": sha(baseline_raw)},
        "method": {"api_calls": 0, "database_changes": 0, "product_changes": 0, "source_changes": 0, "mock_tests": "NOT_RUN", "new_windows_compilation": "NOT_RUN", "pdf_visual_review": "NOT_RUN", "teacher_math_review": "NOT_RUN", "teacher_visual_review": "NOT_RUN"},
        "final_grade": "PENDING_FINAL_ARTIFACTS", "required_count": len(required),
        "common_count": len(common), "optional_excluded_count": len(optional),
        "intermediate_captures": captures, "intermediate_findings": findings,
        "required_checklist": required, "common_checklist": common,
        "optional_excluded_checklist": optional,
        "final_intake_needed": ["frozen approved plan/checkpoints", "exact final generated units and full TeX", "final PDF and page renders", "global review and compiler/checker evidence", "source ZIP and independent rebuild evidence"],
    }
    (output / "audit-preparation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# CH03 最终审计准备（中间版本，不是最终结论）", "", f"任务 `{RUN_ID}`；批准计划 `{PLAN_HASH}`。", "", "已完整读取 CH03 的 22 项 REQUIRED、3 项非必需范围及 G01–G08。以下清单全部等待最终冻结；没有计算最终覆盖率或模型数学准确率。", "", "快照只验证当前状态指向的候选 SHA、计划身份和证据依赖。活跃任务中逐节采集，不代表同一时刻的最终整章。没有数据库、源码、提示词或原稿修改，没有 API 调用。", "", "教师数学验收：**NOT_RUN**；教师逐页视觉：**NOT_RUN**。本次没有编译、PDF 视觉检查或 mock 测试。", "", "## 已保留的中间稿证据", "", "| 节 | 捕获阶段 | 候选 SHA-256 | 快照 |", "|---|---|---|---|"]
    for c in captures:
        lines.append(f"| {c['section_id']} | {c['phase_at_capture']} | `{c['candidate_sha256']}` | [{c['snapshot_candidate']}]({c['snapshot_candidate']}) |")
    lines += ["", "## 中间稿发现", ""]
    for finding in findings:
        lines += [f"- **{finding['id']} / {', '.join(finding['units'])}**：{finding['observation']}  后续：{finding['next_check']}"]
    lines += ["", "S01 的 ε–δ 验证、左右极限充要条件和唯一性推理正确；完整去心邻域前提保证趋近点存在，不机械要求再写聚点术语。S02 的倒数下界和复合去心条件正确。S04 的闭区间端点单侧定义、补值练习正确。S05 明示实数上确界和区间套基础，有界/最值与零点证明链可成立；这不是要求把完备性从头重证。", "", "## 最终逐条证据占位", "", "| 基准 ID | 标题 | 计划节 | 状态 |", "|---|---|---|---|"]
    for row in required:
        lines.append(f"| {row['id']} | {row['title']} | {', '.join(row['planned_sections'])} | PENDING_FINAL |")
    for row in common:
        lines.append(f"| {row['id']} | {row['check']} | 全章 | PENDING_FINAL |")
    lines += ["", "每条最终证据需带 unit ID、TeX 文件 SHA 与行号、PDF SHA 与物理页码、条件/证明/题解解释。以最终全章查漏，不能以中间版本缺失直接给最终 FAIL。所有 PDF 页按 PDF 技能渲染并由 agent 逐页目视；agent 观察与教师签认分开。最终有问题按原工作流修复，不覆盖旧交付文件。", "", "[完整条件与证据占位 JSON](audit-preparation.json)", ""]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(output), "required": 22, "common": 8, "captured_sections": len(captures), "final_grade": "PENDING_FINAL_ARTIFACTS"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
