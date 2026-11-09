"""Score precision/recall/FPR over labeled diffs; gate on baseline regressions."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.correctness import CorrectnessAgent
from agents.performance import PerformanceAgent
from agents.security import SecurityAgent
from agents.style import StyleAgent
from app.core.schemas import DiffChunk, DiffHunk, Finding
from app.services.llm import FakeLLM, HttpLLMClient, LLMClient

CASES_DIR = Path(__file__).parent / "cases"
REPORT_PATH = Path(__file__).parent / "report.md"
BASELINE_PATH = Path(__file__).parent / "baseline.json"

AGENT_MAP = {
    "security": SecurityAgent,
    "performance": PerformanceAgent,
    "correctness": CorrectnessAgent,
    "style": StyleAgent,
}


@dataclass
class Scores:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def fpr(self) -> float:
        # Among predicted findings, fraction that are false positives.
        return self.fp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(CASES_DIR.glob("*.json"))]


def chunk_from_case(case: dict[str, Any]) -> DiffChunk:
    return DiffChunk(
        chunk_id=case["id"],
        file_path=case["file_path"],
        status="modified",
        hunks=[
            DiffHunk(
                header="@@ -1 +1 @@",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=case["diff"].splitlines(),
                new_line_numbers=[2],
                old_line_numbers=[1],
            )
        ],
        estimated_tokens=40,
        content=case["diff"],
    )


def match_finding(finding: Finding, expected: dict[str, Any]) -> bool:
    same_file = finding.file_path == str(expected["file"])
    same_line = finding.line_start == int(expected["line_start"])
    same_cat = finding.category == str(expected["category"])
    return same_file and same_line and same_cat


def fake_response_for_case(case: dict[str, Any], agent_name: str) -> str:
    """Deterministic FakeLLM output keyed off labeled expectations."""
    findings = []
    for exp in case.get("expected", []):
        # Only emit for the responsible agent (or all agents on clean cases → none).
        owner = case.get("agent", "all")
        if owner not in ("all", agent_name):
            continue
        if owner == "all" and not exp:
            continue
        findings.append(
            {
                "file_path": exp["file"],
                "line_start": exp["line_start"],
                "line_end": exp["line_end"],
                "severity": "high",
                "category": exp["category"],
                "title": exp["category"],
                "explanation": "eval fixture",
                "suggested_fix": None,
                "confidence": 0.9,
                "agent_name": agent_name,
            }
        )
    return json.dumps({"findings": findings})


async def run_case(
    case: dict[str, Any],
    *,
    llm_factory: Any,
    use_real: bool,
) -> dict[str, Scores]:
    chunk = chunk_from_case(case)
    agents_to_run = (
        list(AGENT_MAP.keys()) if case.get("agent") == "all" else [case.get("agent", "security")]
    )
    per_agent: dict[str, Scores] = {a: Scores() for a in AGENT_MAP}
    expected = case.get("expected", [])

    for agent_name in agents_to_run:
        if use_real:
            llm: LLMClient = llm_factory()
        else:
            llm = FakeLLM([fake_response_for_case(case, agent_name)])
        agent = AGENT_MAP[agent_name](llm)
        findings = await agent.review(chunk)
        matched_exp: set[int] = set()
        matched_pred: set[int] = set()
        for i, exp in enumerate(expected):
            for j, finding in enumerate(findings):
                if j in matched_pred:
                    continue
                if match_finding(finding, exp):
                    matched_exp.add(i)
                    matched_pred.add(j)
                    per_agent[agent_name].tp += 1
                    break
        per_agent[agent_name].fn += len(expected) - len(matched_exp)
        per_agent[agent_name].fp += len(findings) - len(matched_pred)
        # Clean cases: any finding is FP; already counted. Ensure agents not responsible
        # don't get FN for others' expectations when agent==specific.
        if case.get("agent") not in ("all", agent_name):
            # reset if we shouldn't have run — shouldn't happen
            pass
    # For agents not run on this case, leave zeros.
    return per_agent


def merge_scores(dst: dict[str, Scores], src: dict[str, Scores]) -> None:
    for k, v in src.items():
        dst[k].tp += v.tp
        dst[k].fp += v.fp
        dst[k].fn += v.fn


def overall(scores: dict[str, Scores]) -> Scores:
    out = Scores()
    for s in scores.values():
        out.tp += s.tp
        out.fp += s.fp
        out.fn += s.fn
    return out


def write_report(scores: dict[str, Scores], path: Path) -> None:
    lines = [
        "# ReviewPilot Eval Report",
        "",
        "| agent | precision | recall | false-positive rate | tp | fp | fn |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in scores.items():
        lines.append(
            f"| {name} | {s.precision:.3f} | {s.recall:.3f} | {s.fpr:.3f} | "
            f"{s.tp} | {s.fp} | {s.fn} |"
        )
    tot = overall(scores)
    lines.append(
        f"| **overall** | {tot.precision:.3f} | {tot.recall:.3f} | {tot.fpr:.3f} | "
        f"{tot.tp} | {tot.fp} | {tot.fn} |"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def scores_to_baseline(scores: dict[str, Scores]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, s in scores.items():
        data[name] = {
            "precision": round(s.precision, 4),
            "recall": round(s.recall, 4),
            "fpr": round(s.fpr, 4),
        }
    tot = overall(scores)
    data["overall"] = {
        "precision": round(tot.precision, 4),
        "recall": round(tot.recall, 4),
        "fpr": round(tot.fpr, 4),
    }
    return data


def check_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key, base in baseline.items():
        cur = current.get(key, {})
        base_p = float(base.get("precision", 1.0))
        cur_p = float(cur.get("precision", 1.0))
        if cur_p + 1e-9 < base_p - 0.05:
            failures.append(
                f"{key} precision {cur_p:.3f} dropped >5pts below baseline {base_p:.3f}"
            )
    return failures


async def async_main(*, use_real: bool, write_baseline: bool) -> int:
    cases = load_cases()
    if len(cases) < 20:
        print(f"expected 20+ cases, found {len(cases)}", file=sys.stderr)
        return 2

    def llm_factory() -> LLMClient:
        from app.core.settings import get_settings

        return HttpLLMClient.from_settings(get_settings())

    totals: dict[str, Scores] = {a: Scores() for a in AGENT_MAP}
    for case in cases:
        # For clean cases run all agents; for labeled, run owning agent only once
        # but still track overall via merge.
        if case.get("agent") == "all":
            result = await run_case(case, llm_factory=llm_factory, use_real=use_real)
        else:
            result = await run_case(case, llm_factory=llm_factory, use_real=use_real)
        merge_scores(totals, result)

    write_report(totals, REPORT_PATH)
    current = scores_to_baseline(totals)
    if write_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"wrote baseline to {BASELINE_PATH}")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    failures = check_baseline(current, baseline)
    print(REPORT_PATH.read_text(encoding="utf-8"))
    if failures:
        for f in failures:
            print(f"REGRESSION: {f}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-model", action="store_true", help="Call the configured LLM")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(async_main(use_real=args.real_model, write_baseline=args.write_baseline))
    )


if __name__ == "__main__":
    main()
