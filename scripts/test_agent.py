"""
Agent evaluation & debug harness — run pipeline agents one at a time on a cached case.

Examples (from the project root):

  python scripts/test_agent.py --case MFL001 --agent financial_analysis
  python scripts/test_agent.py --case MFL001 --agent all --stop-after policy
  python scripts/test_agent.py --agent financial_analysis --cases APOL001,MFL001
  python scripts/test_agent.py --case MFL001 --agent narrative                       # plan: prompts, no LLM
  python scripts/test_agent.py --case MFL001 --agent narrative --narrative-mode llm --sections financial_analysis
  python scripts/test_agent.py --case MFL001 --agent narrative --narrative-mode full  # the real 21-section CAM
  python scripts/test_agent.py --case MFL001 --agent validation --save before
  python scripts/test_agent.py --case MFL001 --agent validation --compare before
  python scripts/test_agent.py --list
  python scripts/test_agent.py --snapshots --cases APOL001,MFL001

Every run is also written as JSON to output/agent_harness/runs/.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CAM pipeline agents individually on a cached case snapshot.")
    parser.add_argument("--case", help="Entity ID, e.g. MFL001")
    parser.add_argument("--cases", help="Comma-separated entity IDs to compare, e.g. APOL001,MFL001")
    parser.add_argument("--agent", default="all", help="Agent name or 'all'")
    parser.add_argument("--stop-after", help="Last agent to run (with --agent all)")
    parser.add_argument("--narrative-mode", default="plan", choices=["plan", "template", "llm", "full"],
                        help="plan: fact pack + prompts, no LLM (default); template: template CAM; "
                             "llm: send --sections to the LLM; full: the production 21-section LLM CAM")
    parser.add_argument("--sections", help="Comma-separated CAM section ids for --narrative-mode llm")
    parser.add_argument("--no-checkpoints", action="store_true", help="full mode: ignore saved section checkpoints")
    parser.add_argument("--refresh-snapshot", action="store_true", help="Re-run data_ingestion instead of the cache")
    parser.add_argument("--no-downstream", action="store_true",
                        help="Do not run later agents (faster; downstream consumption is then not observed)")
    parser.add_argument("--json", action="store_true", help="Print the machine-readable report")
    parser.add_argument("--show-output", action="store_true", help="Print the raw agent output")
    parser.add_argument("--show-prompts", action="store_true", help="Print the full prompts / responses")
    parser.add_argument("--save", metavar="LABEL", help="Save the result as a baseline (e.g. before)")
    parser.add_argument("--compare", metavar="LABEL", help="Compare with a saved baseline (BEFORE → AFTER)")
    parser.add_argument("--post-pipeline", action="store_true",
                        help="Build the case record (M1–M6, and the final CAM) from the snapshot and check those outputs")
    parser.add_argument("--list", action="store_true", help="List agents and what each does (from the code)")
    parser.add_argument("--snapshots", action="store_true", help="Show snapshot status for --case/--cases")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show application logs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    from src.core.env_loader import load_local_env
    load_local_env()
    from src.core.config_manager import config
    config.load()
    from src.devtools import agent_harness as h
    from src.devtools.agent_contracts import AGENT_ORDER, CONTRACTS

    cases = [c.strip() for c in (args.cases or args.case or "").split(",") if c.strip()]
    if args.list:
        for name in AGENT_ORDER:
            c = CONTRACTS[name]
            print(f"{name}\n  purpose: {c['purpose']}\n  llm: {'yes' if c['prompt'] else 'no'}\n  outputs: "
                  + ", ".join(f"{k} → {', '.join(c['consumers'].get(k) or ['NOT CONSUMED'])}" for k in c["outputs"]))
        return 0
    if args.snapshots:
        print(json.dumps(h.snapshot_status(cases), indent=2))
        return 0
    if not cases:
        parser.error("give --case or --cases")

    if args.post_pipeline:
        worst = 0
        for case_id in cases:
            case = h.build_case_from_snapshot(case_id, refresh_snapshot=args.refresh_snapshot)
            print(f"\n=== {case_id}: agents " +", ".join(f"{a} {r['status']}" for a, r in case["_agent_reports"].items()))
            for c in h.validate_case_outputs(case):
                print(f"  [{c['status'].upper():4}] {c['check']}: {c['detail']}")
                worst = max(worst, 1 if c["status"] == "fail" else 0)
        return worst

    sections = [s.strip() for s in (args.sections or "").split(",") if s.strip()] or None
    all_reports, exit_code = [], 0
    for case in cases:
        result = h.run_case(case, agents=args.agent, stop_after=args.stop_after, narrative_mode=args.narrative_mode,
                            sections=sections, refresh_snapshot=args.refresh_snapshot,
                            observe_downstream=not args.no_downstream, use_checkpoints=not args.no_checkpoints)
        path = h.save_run(result)
        snap = result["snapshot"]
        print(f"\n=== {case}: snapshot {snap['source']} ({snap['path']}){' — ' + snap['stale_reason'] if snap.get('stale_reason') else ''}")
        print(f"    executed: {' → '.join(result['executed'])}    report: {path}")
        for rep in result["reports"]:
            all_reports.append(rep)
            if args.json:
                print(json.dumps(rep if args.show_output else h.strip_heavy(rep), indent=2, default=str,
                                 ensure_ascii=False))
            else:
                print("\n" + h.render_report(rep, show_output=args.show_output, show_prompts=args.show_prompts))
            if args.save:
                print(f"\nSaved baseline '{args.save}': {h.save_baseline(rep, args.save)}")
            if args.compare:
                print("\n" + h.render_baseline_diff(h.compare_with_baseline(rep, args.compare)))
            exit_code = max(exit_code, 1 if rep["status"] == "FAIL" else 0)
    if len(all_reports) > 1:
        print("\n=== Comparison\n" + h.render_comparison(h.comparison_rows(all_reports)))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
