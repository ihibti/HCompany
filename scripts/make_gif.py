#!/usr/bin/env python3
"""Capture replay frames with headless Chrome and assemble animated GIFs.

Frames come from the app's replay UI: ``/replay/<audit>?at=N`` freezes a
single-audit replay after N emitted steps; ``POST /api/batches`` with
``replay`` + ``at`` does the same per audit for multi-column races. A final
unfrozen frame shows the end state (grade badge + headline).

Usage:
    uv run python scripts/make_gif.py --single <audit_id> --out docs/assets/x.gif
    uv run python scripts/make_gif.py --batch <id1,id2,id3> --out docs/assets/y.gif
    uv run python scripts/make_gif.py --preset l5 --out docs/assets/netflux-l5.gif
    uv run python scripts/make_gif.py --preset french --out docs/assets/french-media-race.gif
"""

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
REPO = Path(__file__).resolve().parent.parent
DEFAULT_SERVER = "http://127.0.0.1:8765"

FRENCH_RACE = [
    "20261107-234439-20minutes-fr-refuse_cookies",
    "20261107-233259-ouest-france-fr-refuse_cookies",
    "20261107-222321-lefigaro-fr-refuse_cookies",
]


def _post_batch(server: str, ids: list[str], at: int | None, speed: float) -> str:
    body = json.dumps({"replay": ids, "at": at, "speed": speed}).encode()
    req = urllib.request.Request(
        f"{server}/api/batches", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["batch_id"]


def _audit_steps(audit_id: str, store_dirs=("runs", "demo_runs")) -> int:
    for sd in store_dirs:
        p = REPO / sd / audit_id / "audit.json"
        if p.exists():
            a = json.loads(p.read_text())
            n = len(a["leave"].get("steps") or [])
            if a.get("enter"):
                n += len(a["enter"].get("steps") or [])
            return n
    return 12


def _latest_l5_audit() -> str:
    """Latest pro level-5 audit id across benchmark files."""
    best = None
    for bp in sorted((REPO / "runs" / "benchmarks").glob("*.json")):
        try:
            data = json.loads(bp.read_text())
        except Exception:
            continue
        if data.get("agent") != "h/web-surfer-pro":
            continue
        for row in data.get("levels", []):
            if row.get("level") == 5 and row.get("audit_id"):
                best = row["audit_id"]
    if not best:
        sys.exit("no pro level-5 audit found in runs/benchmarks")
    return best


async def _capture(jobs: list[tuple[str, float, Path]], w: int, h: int) -> None:
    """jobs: (url, settle_seconds, out_png). One headless Chrome, sequential."""
    port = 9700 + int(time.time()) % 300
    proc = subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={port}",
        f"--window-size={w},{h}", "--hide-scrollbars", "--mute-audio",
        f"--user-data-dir=/tmp/gif-profile-{port}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = None
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json", timeout=1))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.25)
        if page is None:
            raise RuntimeError("chrome did not start")
        async with websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=50_000_000) as ws:
            mid = 0

            async def send(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps(
                    {"id": mid, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        return msg.get("result", {})

            await send("Page.enable")
            await send("Emulation.setDeviceMetricsOverride", {
                "width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
            for i, (url, settle, out) in enumerate(jobs):
                await send("Page.navigate", {"url": url})
                await asyncio.sleep(settle)
                shot = await send("Page.captureScreenshot", {"format": "png"})
                out.write_bytes(base64.b64decode(shot["data"]))
                print(f"  frame {i + 1}/{len(jobs)} <- {url} -> {out.name}",
                      flush=True)
    finally:
        proc.terminate()


def _build_gif(frames: list[Path], out: Path, width: int = 1200,
               step_ms: int = 850, last_ms: int = 3000) -> None:
    imgs = []
    for p in frames:
        im = Image.open(p).convert("RGB")
        h = round(im.height * width / im.width)
        imgs.append(im.resize((width, h), Image.LANCZOS))
    duration = [step_ms] * (len(imgs) - 1) + [last_ms]
    # stay under ~8MB: drop colors/width if needed
    for colors, w in ((256, width), (192, width), (128, int(width * 0.85))):
        if w != width:
            imgs = [im.resize((w, round(im.height * w / width)), Image.LANCZOS)
                    for im in imgs]
        pal = [im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
               for im in imgs]
        out.parent.mkdir(parents=True, exist_ok=True)
        pal[0].save(out, save_all=True, append_images=pal[1:],
                    duration=duration, loop=0, optimize=True,
                    disposal=2)
        size = out.stat().st_size
        if size < 8 * 1024 * 1024:
            print(f"wrote {out} ({size / 1e6:.1f} MB, {len(imgs)} frames)")
            return
    print(f"wrote {out} ({size / 1e6:.1f} MB — over 8MB target)", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--single", help="audit id for a single-column replay GIF")
    ap.add_argument("--batch", help="comma-separated audit ids for a race GIF")
    ap.add_argument("--preset", choices=["l5", "french"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    tmp = Path("/tmp/eh-gif-frames")
    tmp.mkdir(exist_ok=True)
    for old in tmp.glob("*.png"):
        old.unlink()

    jobs: list[tuple[str, float, Path]] = []
    if args.preset == "l5":
        args.single = _latest_l5_audit()
        print(f"preset l5 -> {args.single}")
    if args.preset == "french":
        args.batch = ",".join(FRENCH_RACE)
        print(f"preset french -> {args.batch}")

    if args.single:
        total = _audit_steps(args.single)
        speed = 5.0
        # one frame per emitted step, then the finished end state
        for n in range(1, total + 1):
            url = (f"{args.server}/replay/{args.single}"
                   f"?at={n}&speed={speed:g}")
            settle = min(8.0, 2.0 + n * (0.9 / speed) + 1.2)
            jobs.append((url, settle, tmp / f"s{n:02d}.png"))
        jobs.append((f"{args.server}/replay/{args.single}?speed={speed:g}",
                     min(15.0, 4.0 + total * (0.9 / speed) + 2.0),
                     tmp / "final.png"))
    elif args.batch:
        ids = [s.strip() for s in args.batch.split(",") if s.strip()]
        if not (2 <= len(ids) <= 3):
            sys.exit("--batch needs 2-3 audit ids")
        speed = 5.0
        # freeze frames: each audit parks after its own nth step
        for n in (1, 2, 3, 4, 5, 7):
            bid = _post_batch(args.server, ids, n, speed)
            jobs.append((f"{args.server}/run/{bid}", 3.5, tmp / f"b{n:02d}.png"))
        bid = _post_batch(args.server, ids, None, speed)
        jobs.append((f"{args.server}/run/{bid}", 9.0, tmp / "final.png"))
    else:
        sys.exit("give --single, --batch or --preset")

    asyncio.run(_capture(jobs, args.width, args.height))
    frames = sorted(tmp.glob("*.png"),
                    key=lambda p: (p.name != "final.png", p.name))
    _build_gif(frames, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
