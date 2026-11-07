"""Escape Hatch CLI: batch audits, gauntlet benchmark, report re-render."""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from escapehatch.gauntlet import load_levels, pattern_recall, verify_gauntlet
from escapehatch.models import Audit
from escapehatch.pipeline import run_audit, shot_resolver
from escapehatch.prompts import Task
from escapehatch.report import render_report_html
from escapehatch.store import RunStore

logger = logging.getLogger("escapehatch")

GAUNTLET_DIR = Path(__file__).resolve().parent.parent.parent / "gauntlet"
LEVELS_JSON = GAUNTLET_DIR / "levels.json"
GAUNTLET_CREDENTIALS = "email demo@netflux.test, password Hatch-2026"

_SESSION_LIMIT = 3


class _WeightedSemaphore:
    """Caps total in-flight sessions (an audit with enter uses 2)."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._active = 0
        self._cond = asyncio.Condition()

    async def acquire(self, n: int) -> None:
        async with self._cond:
            while self._active + n > self._limit:
                await self._cond.wait()
            self._active += n

    async def release(self, n: int) -> None:
        async with self._cond:
            self._active -= n
            self._cond.notify_all()

    def __call__(self, n: int):
        return _Acquire(self, n)


class _Acquire:
    def __init__(self, sem: _WeightedSemaphore, n: int) -> None:
        self._sem, self._n = sem, n

    async def __aenter__(self) -> None:
        await self._sem.acquire(self._n)

    async def __aexit__(self, *exc) -> None:
        await self._sem.release(self._n)


def parse_levels(spec: str) -> list[int]:
    """Parse '1-5', '2', '1,3,5', '1-3,5' into sorted unique level numbers."""
    levels: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            if lo > hi or lo < 1:
                raise ValueError(f"bad range {part!r}")
            levels.update(range(lo, hi + 1))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"bad level {part!r}")
            levels.add(n)
    if not levels:
        raise ValueError("empty level spec")
    return sorted(levels)


def _progress_printer(verbose: bool, extra: dict[str, Any] | None = None):
    async def on_update(msg: dict) -> None:
        if extra is not None and msg.get("type") == "confirm_request":
            extra.setdefault("confirmations", []).append(
                {"journey": msg.get("journey"), "action": msg.get("action")}
            )
        t = msg.get("type")
        if t == "step" and verbose:
            step = msg.get("step") or {}
            print(
                f"    [{msg.get('journey')}] #{step.get('index')} {step.get('action')}"
                f" {step.get('element') or ''}".rstrip(),
                file=sys.stderr,
            )
        elif t == "confirm_request":
            print(f"    !! confirm [{msg.get('journey')}] {msg.get('action')}", file=sys.stderr)
        elif t == "error":
            print(f"    !! error: {msg.get('message')}", file=sys.stderr)
    return on_update


def _effort_str(audit: Audit) -> str:
    lv = audit.score.leave_effort.total
    if audit.enter is not None and audit.score.enter_effort is not None:
        return f"{lv}/{audit.score.enter_effort.total}"
    return str(lv)


async def _cmd_audit(args: argparse.Namespace) -> int:
    store = RunStore(args.store)
    sem = _WeightedSemaphore(_SESSION_LIMIT)
    results: list[Audit] = []

    async def one(url: str) -> Audit:
        weight = 2 if args.enter else 1
        async with sem(weight):
            audit = await run_audit(
                site_url=url,
                task=Task(args.task),
                store=store,
                agent=args.agent,
                with_enter=args.enter,
                credentials=args.credentials,
                on_update=_progress_printer(args.verbose),
                max_steps=args.max_steps,
                max_time_s=args.max_time,
            )
            results.append(audit)
            print(
                f"  {url}: grade {audit.score.grade} friction {audit.score.friction}"
                f" effort {_effort_str(audit)} findings {len(audit.findings)}"
                f" cost ${audit.leave.cost_usd or 0:.4f} -> {audit.id}",
                file=sys.stderr,
            )
            return audit

    await asyncio.gather(*(one(u) for u in args.urls))

    print(f"\n{'site':38} {'grade':5} {'friction':8} {'effort L/E':10} {'findings':8} {'cost':8}")
    print("-" * 82)
    for a in sorted(results, key=lambda x: x.site_url):
        print(
            f"{a.site_url:38} {a.score.grade:5} {a.score.friction:<8}"
            f" {_effort_str(a):10} {len(a.findings):<8} ${a.leave.cost_usd or 0:<7.4f}"
        )
    return 0


async def _cmd_gauntlet(args: argparse.Namespace) -> int:
    store = RunStore(args.store)
    levels_all = load_levels(LEVELS_JSON)
    wanted = set(parse_levels(args.levels))
    levels = [l for l in levels_all if l.level in wanted]
    if not levels:
        print("no matching levels", file=sys.stderr)
        return 1

    base = args.base if args.base.endswith("/") else args.base + "/"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bench_path = Path(args.store) / "benchmarks" / f"{stamp}-{args.agent.replace('/', '-')}.json"
    bench_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for level in levels:
        leave_url = urljoin(base, level.start_path)
        signup_url = urljoin(base, level.signup_path)
        print(f"[L{level.level}] {level.title}: leave {leave_url}", file=sys.stderr)
        t0 = time.monotonic()
        collected: dict[str, Any] = {}
        audit = await run_audit(
            site_url=leave_url,
            task=Task.CANCEL_SUBSCRIPTION,
            store=store,
            agent=args.agent,
            with_enter=True,
            credentials=GAUNTLET_CREDENTIALS,
            enter_url=signup_url,
            on_update=_progress_printer(args.verbose, collected),
            max_steps=args.max_steps,
            max_time_s=args.max_time,
        )
        wall = time.monotonic() - t0
        verdict = verify_gauntlet(audit.leave, level)
        precision, recall = pattern_recall(audit.findings, level)
        leave_eff = audit.score.leave_effort.total
        row = {
            "level": level.level,
            "title": level.title,
            "audit_id": audit.id,
            "verdict": verdict,
            "leave_effort": leave_eff,
            "min_leave_interactions": level.min_leave_interactions,
            "enter_effort": audit.score.enter_effort.total if audit.score.enter_effort else None,
            "grade": audit.score.grade,
            "friction": audit.score.friction,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "patterns_found": [f.pattern for f in audit.findings],
            "patterns_truth": level.patterns,
            "cost_usd": round((audit.leave.cost_usd or 0) + ((audit.enter.cost_usd or 0) if audit.enter else 0), 4),
            "wall_seconds": round(wall, 1),
            "leave_duration_s": audit.leave.duration_s,
            "confirmations": collected.get("confirmations", []),
        }
        rows.append(row)
        print(
            f"[L{level.level}] {verdict} effort {leave_eff}/{level.min_leave_interactions}"
            f" grade {audit.score.grade} P/R {precision:.2f}/{recall:.2f}"
            f" ${row['cost_usd']:.3f} {row['wall_seconds']}s",
            file=sys.stderr,
        )

    bench = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent": args.agent,
        "base": base,
        "levels": rows,
    }
    bench_path.write_text(json.dumps(bench, indent=2, ensure_ascii=False))

    print(f"\n{'lvl':4} {'verdict':12} {'effort':10} {'grade':5} {'P':5} {'R':5} {'cost':8} {'wall':7} audit")
    print("-" * 100)
    for r in rows:
        print(
            f"{r['level']:<4} {r['verdict']:12} {r['leave_effort']}/{r['min_leave_interactions']:<8}"
            f" {r['grade']:5} {r['precision']:<5} {r['recall']:<5}"
            f" ${r['cost_usd']:<7.4f} {r['wall_seconds']:<7} {r['audit_id']}"
        )
    print(f"\nbenchmark written to {bench_path}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    store = RunStore(args.store)
    audit = store.load_audit(args.audit_id)
    audit_dir = store.root / audit.id
    html = render_report_html(audit, shot_resolver(store, audit_dir))
    out = audit_dir / "report.html"
    out.write_text(html)
    print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="escapehatch", description="Measure how hard sites make it to leave.")
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("audit", help="Audit one or more sites")
    pa.add_argument("urls", nargs="+", help="site URLs to audit")
    pa.add_argument("--task", default="refuse_cookies", choices=[t.value for t in Task])
    pa.add_argument("--agent", default="h/web-surfer-pro")
    pa.add_argument("--no-enter", dest="enter", action="store_false", help="skip the enter counterpart journey")
    pa.set_defaults(enter=True)
    pa.add_argument("--store", default="runs")
    pa.add_argument("--credentials", default=None)
    pa.add_argument("--max-steps", type=int, default=35)
    pa.add_argument("--max-time", type=int, default=480)
    pa.add_argument("-v", "--verbose", action="store_true")
    pa.set_defaults(func=_cmd_audit)

    pg = sub.add_parser("gauntlet", help="Run the Netflux benchmark levels")
    pg.add_argument("--levels", default="1-5", help="e.g. 1-5, 2, 1,3,5")
    pg.add_argument("--agent", default="h/web-surfer-pro")
    pg.add_argument("--base", default="https://ihibti.github.io/HCompany/")
    pg.add_argument("--store", default="runs")
    pg.add_argument("--max-steps", type=int, default=35)
    pg.add_argument("--max-time", type=int, default=480)
    pg.add_argument("-v", "--verbose", action="store_true")
    pg.set_defaults(func=_cmd_gauntlet)

    pr = sub.add_parser("report", help="Re-render a stored audit's report.html")
    pr.add_argument("audit_id")
    pr.add_argument("--store", default="runs")
    pr.set_defaults(func=_cmd_report)

    return p


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()
    try:
        code = asyncio.run(args.func(args))
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
