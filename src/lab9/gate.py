"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_bad_number(v: object) -> bool:
    if v is None or isinstance(v, bool):
        return v is None
    if isinstance(v, (int, float)):
        return math.isnan(v) or math.isinf(v)
    return True


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")

    pr_metrics = pr.get("metrics") or {}
    if not pr_metrics:
        problems.append("metrics dict is empty")
    for k, v in pr_metrics.items():
        if _is_bad_number(v):
            problems.append(f"metric {k!r} is missing/NaN/inf: {v!r}")

    for m in spec.get("metrics") or []:
        mid = m["id"]
        if mid not in pr_metrics or _is_bad_number(pr_metrics.get(mid)):
            problems.append(f"spec metric {mid!r} missing or invalid in pr['metrics']")

    pr_manifest = pr.get("manifest") or {}
    base_manifest = base.get("manifest") or {}
    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []

    pr_items = int(pr_manifest.get("items") or 0)
    pr_seeds = list(pr_manifest.get("seeds") or [])
    expected_rows = pr_items * len(pr_seeds)
    if len(pr_rows) != expected_rows:
        problems.append(f"len(rows)={len(pr_rows)} != manifest items*seeds ({expected_rows})")
    if len(pr_rows) != len(base_rows):
        problems.append(f"len(rows)={len(pr_rows)} != baseline len(rows)={len(base_rows)}")
    if pr_items != int(base_manifest.get("items") or 0) or set(pr_seeds) != set(base_manifest.get("seeds") or []):
        problems.append("manifest items or seeds differ from baseline")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    base_pairs = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if len(set(pr_pairs)) != len(pr_rows):
        problems.append("duplicate (item_id, seed) rows in PR report")
    if set(pr_pairs) != set(base_pairs):
        problems.append("PR (item_id, seed) set differs from baseline")

    row_metric_ids = [
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS
        or any(m["id"] in r for r in base_rows)
        or any(m["id"] in r for r in pr_rows)
    ]
    for r in pr_rows:
        for mid in row_metric_ids:
            val = r.get(mid)
            if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has invalid {mid}={val!r}")

    if not problems and pr_rows:
        for mid in row_metric_ids:
            if mid in pr_metrics and all(r.get(mid) is not None for r in pr_rows):
                vals = [bool(r[mid]) for r in pr_rows]
                exp = sum(vals) if mid in ("secret_leak", "approval_bypass") else round(sum(vals) / len(vals), 4)
                if abs(float(pr_metrics[mid]) - float(exp)) > 1e-3:
                    problems.append(f"metric {mid!r}={pr_metrics[mid]} disagrees with rows aggregate {exp}")
        if "pass_hat_5" in pr_metrics and any("pass_rate" in r for r in pr_rows) and len(pr_seeds) == 5:
            by_item: dict[str, list[bool]] = {}
            for r in pr_rows:
                by_item.setdefault(str(r.get("item_id")), []).append(bool(r.get("pass_rate")))
            if by_item and all(len(v) == 5 for v in by_item.values()):
                exp_ph5 = round(sum(all(v) for v in by_item.values()) / len(by_item), 4)
                if abs(float(pr_metrics["pass_hat_5"]) - exp_ph5) > 1e-3:
                    problems.append(f"metric 'pass_hat_5'={pr_metrics['pass_hat_5']} disagrees with rows {exp_ph5}")

    base_slices_by_pair = {
        (r.get("item_id"), r.get("seed")): sorted(r.get("slices") or [])
        for r in base_rows
    }
    base_slices_by_item = {
        r.get("item_id"): sorted(r.get("slices") or [])
        for r in base_rows
    }
    for r in pr_rows:
        pair = (r.get("item_id"), r.get("seed"))
        r_slices = sorted(r.get("slices") or [])
        if pair in base_slices_by_pair and r_slices != base_slices_by_pair[pair]:
            problems.append(f"slice tags for {pair[0]}@{pair[1]} differ from baseline")
        elif r.get("item_id") in base_slices_by_item and r_slices != base_slices_by_item[r.get("item_id")]:
            problems.append(f"slice tags for {r.get('item_id')} differ from baseline")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        cur_m = {m["id"]: m for m in (spec.get("metrics") or [])}
        old_m = {m["id"]: m for m in (base_spec.get("metrics") or [])}
        for mid, bm in old_m.items():
            if mid not in cur_m:
                problems.append(f"ratchet: metric {mid!r} removed from spec")
                continue
            pm = cur_m[mid]
            if bm.get("blocking") and not pm.get("blocking"):
                problems.append(f"ratchet: metric {mid!r} changed from blocking to non-blocking")
            bth = bm.get("threshold") or {}
            pth = pm.get("threshold") or {}
            if "min" in bth and ("min" not in pth or pth["min"] < bth["min"]):
                problems.append(f"ratchet: metric {mid!r} min threshold lowered or removed")
            if "max" in bth and ("max" not in pth or pth["max"] > bth["max"]):
                problems.append(f"ratchet: metric {mid!r} max threshold raised or removed")
            if "max_increase" in bth and ("max_increase" not in pth or pth["max_increase"] > bth["max_increase"]):
                problems.append(f"ratchet: metric {mid!r} max_increase threshold raised or removed")
            if bth.get("no_significant_drop") and not pth.get("no_significant_drop"):
                problems.append(f"ratchet: metric {mid!r} dropped no_significant_drop")

        cur_s = {(s["name"], s["metric"]): s for s in (spec.get("slices") or [])}
        old_s = {(s["name"], s["metric"]): s for s in (base_spec.get("slices") or [])}
        for skey, bs_entry in old_s.items():
            sname = f"{skey[0]}/{skey[1]}"
            if skey not in cur_s:
                problems.append(f"ratchet: slice {sname!r} removed from spec")
                continue
            ps_entry = cur_s[skey]
            if bs_entry.get("blocking", True) and not ps_entry.get("blocking", True):
                problems.append(f"ratchet: slice {sname!r} changed from blocking to non-blocking")
            if "min" in bs_entry and ("min" not in ps_entry or ps_entry["min"] < bs_entry["min"]):
                problems.append(f"ratchet: slice {sname!r} min threshold lowered or removed")
            if "max" in bs_entry and ("max" not in ps_entry or ps_entry["max"] > bs_entry["max"]):
                problems.append(f"ratchet: slice {sname!r} max threshold raised or removed")
            if bs_entry.get("no_significant_drop") and not ps_entry.get("no_significant_drop"):
                problems.append(f"ratchet: slice {sname!r} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name = s["name"]
        mid = s["metric"]
        sid = f"slice:{name}/{mid}"
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in s and val > s["max"]:
            verdict = "fail"
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        if s.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        is_blocking = bool(s.get("blocking", True))
        if verdict != "ok" and is_blocking:
            blocked.append(sid)
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if is_blocking else "warn")
        lines.append(f"  {sid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
