from __future__ import annotations

import argparse
import csv
import ctypes
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import ImageGrab, ImageStat

user32 = ctypes.windll.user32
SW_RESTORE = 9
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


@dataclass
class Sample:
    t: float
    luma: float
    black_ratio: float
    diff: float


def find_position_window() -> Optional[int]:
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "Καταγραφή Θέσεων" in title or "ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ" in title.upper():
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def client_bbox(hwnd: int):
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetClientRect failed")
    pt = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        raise RuntimeError("ClientToScreen failed")
    return (pt.x, pt.y, pt.x + rect.right, pt.y + rect.bottom)


def frame_metrics(img, prev_small=None):
    small = img.resize((180, 110)).convert("RGB")
    stat = ImageStat.Stat(small)
    mean = stat.mean
    luma = 0.2126 * mean[0] + 0.7152 * mean[1] + 0.0722 * mean[2]

    pixels = list(small.getdata())
    black = sum(1 for r, g, b in pixels if r <= 8 and g <= 8 and b <= 8)
    black_ratio = black / len(pixels)

    diff = 0.0
    if prev_small is not None:
        a = list(prev_small.getdata())
        total = 0
        for (r1,g1,b1),(r2,g2,b2) in zip(a,pixels):
            total += abs(r1-r2)+abs(g1-g2)+abs(b1-b2)
        diff = total / (len(pixels)*3*255.0)
    return luma, black_ratio, diff, small


def capture_sequence(hwnd: int, seconds: float, interval: float = 0.025):
    bbox = client_bbox(hwnd)
    samples = []
    raw = []
    prev = None
    start = time.perf_counter()
    while True:
        now = time.perf_counter()
        if now - start > seconds:
            break
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        luma, black, diff, prev2 = frame_metrics(img, prev)
        samples.append(Sample(now-start, luma, black, diff))
        raw.append((now-start, img.copy()))
        prev = prev2
        elapsed = time.perf_counter() - now
        if elapsed < interval:
            time.sleep(interval-elapsed)
    return samples, raw


def summarize(samples):
    if not samples:
        return {}
    stable = samples[max(0, int(len(samples)*0.65)):]
    baseline_luma = sum(s.luma for s in stable)/len(stable)
    baseline_black = sum(s.black_ratio for s in stable)/len(stable)
    min_luma = min(s.luma for s in samples)
    max_black = max(s.black_ratio for s in samples)
    max_diff = max(s.diff for s in samples)

    suspect = [
        s for s in samples
        if (baseline_luma > 1 and s.luma < baseline_luma * 0.55)
        or s.black_ratio > max(0.15, baseline_black + 0.20)
        or s.diff > 0.22
    ]
    return {
        "frames": len(samples),
        "baseline_luma": round(baseline_luma, 3),
        "baseline_black_ratio": round(baseline_black, 5),
        "min_luma": round(min_luma, 3),
        "max_black_ratio": round(max_black, 5),
        "max_frame_diff": round(max_diff, 5),
        "suspect_frames": len(suspect),
        "flicker_detected": bool(suspect),
    }


def normalized_image_distance(img_a, img_b) -> float:
    a = img_a.resize((180, 110)).convert("RGB")
    b = img_b.resize((180, 110)).convert("RGB")
    pa = list(a.getdata())
    pb = list(b.getdata())
    total = 0
    for (r1,g1,b1),(r2,g2,b2) in zip(pa,pb):
        total += abs(r1-r2)+abs(g1-g2)+abs(b1-b2)
    return total / (len(pa)*3*255.0)


def startup_endpoint_check(raw, out_dir: Path, prefix: str, threshold: float = 0.08):
    if not raw:
        return {"endpoint_anomaly_frames": 0, "max_endpoint_distance": 0.0}
    final_ref = raw[-1][1]
    scored = [(t, normalized_image_distance(img, final_ref), img) for t, img in raw]
    anomalies = [x for x in scored if x[1] > threshold]
    for rank, (t, dist, img) in enumerate(sorted(scored, key=lambda x: x[1], reverse=True)[:5], 1):
        img.save(out_dir / f"{prefix}_endpoint_{rank:02d}_{t:.3f}s_d{dist:.3f}.png")
    return {
        "endpoint_anomaly_frames": len(anomalies),
        "max_endpoint_distance": round(max(x[1] for x in scored), 5),
        "endpoint_flicker_detected": bool(anomalies),
    }


def transition_endpoint_check(pre_raw, post_raw, out_dir: Path, prefix: str, threshold: float = 0.08):
    if not pre_raw or not post_raw:
        return {"third_state_frames": 0, "max_third_state_distance": 0.0}
    pre_ref = pre_raw[-1][1]
    post_ref = post_raw[-1][1]
    scored = []
    for t, img in pre_raw:
        scored.append((t, min(normalized_image_distance(img, pre_ref), normalized_image_distance(img, post_ref)), img))
    offset = pre_raw[-1][0] + 0.025
    for t, img in post_raw:
        scored.append((t + offset, min(normalized_image_distance(img, pre_ref), normalized_image_distance(img, post_ref)), img))
    anomalies = [x for x in scored if x[1] > threshold]
    for rank, (t, dist, img) in enumerate(sorted(scored, key=lambda x: x[1], reverse=True)[:5], 1):
        img.save(out_dir / f"{prefix}_endpoint_{rank:02d}_{t:.3f}s_d{dist:.3f}.png")
    return {
        "third_state_frames": len(anomalies),
        "max_third_state_distance": round(max(x[1] for x in scored), 5),
        "endpoint_flicker_detected": bool(anomalies),
    }


def save_worst(raw, samples, out_dir: Path, prefix: str):
    if not samples:
        return
    ranked = sorted(range(len(samples)), key=lambda i: (
        samples[i].black_ratio,
        samples[i].diff,
        -samples[i].luma
    ), reverse=True)[:5]
    for rank, i in enumerate(ranked, 1):
        t, img = raw[i]
        img.save(out_dir / f"{prefix}_worst_{rank:02d}_{t:.3f}s.png")


def write_csv(samples, path: Path):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["t_s","luma","black_ratio","frame_diff"])
        for s in samples:
            w.writerow([f"{s.t:.4f}",f"{s.luma:.4f}",f"{s.black_ratio:.6f}",f"{s.diff:.6f}"])


def click_theme(hwnd: int):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    left, top, right, bottom = client_bbox(hwnd)
    width = right-left
    # The last 86px of the header belong to the Greece map, not the
    # theme button. The main window has 28px outer and 20px header margins,
    # a 16px widget gap, and a 108px theme-button minimum width.
    x = left + width - (28 + 20 + 86 + 16 + 108 // 2)
    y = top + 22 + 12 + 34 // 2
    user32.SetCursorPos(x, y)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def wait_for_window(pid: int, timeout=20.0):
    end = time.time()+timeout
    while time.time() < end:
        hwnd = find_position_window()
        if hwnd:
            return hwnd
        time.sleep(0.01)
    raise RuntimeError("Main window not found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    exe = str(Path(args.exe).resolve())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report = {"startup_runs": [], "theme_toggles": [], "capture_supported": True}

    for run in range(1, 21):
        p = subprocess.Popen([exe], cwd=str(Path(exe).parent))
        try:
            hwnd = wait_for_window(p.pid)
            samples, raw = capture_sequence(hwnd, 1.2)
            summary = summarize(samples)
            summary.update(startup_endpoint_check(raw, out, f"startup_{run:02d}"))
            summary["run"] = run
            report["startup_runs"].append(summary)
            write_csv(samples, out / f"startup_{run:02d}.csv")
            save_worst(raw, samples, out, f"startup_{run:02d}")
        finally:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(3)
                except subprocess.TimeoutExpired:
                    p.kill()
        time.sleep(0.6)

    p = subprocess.Popen([exe], cwd=str(Path(exe).parent))
    try:
        hwnd = wait_for_window(p.pid)
        time.sleep(0.8)
        for toggle in range(1, 31):
            pre, pre_raw = capture_sequence(hwnd, 0.25)
            click_theme(hwnd)
            post, post_raw = capture_sequence(hwnd, 0.65)
            combined = list(pre)
            offset = pre[-1].t + 0.025 if pre else 0
            combined.extend(Sample(s.t+offset, s.luma, s.black_ratio, s.diff) for s in post)
            raw = pre_raw + [(t+offset,img) for t,img in post_raw]
            summary = summarize(combined)
            summary.update(transition_endpoint_check(pre_raw, post_raw, out, f"theme_{toggle:02d}"))
            summary["toggle"] = toggle
            if pre and post:
                summary["pre_mean_luma"] = round(sum(x.luma for x in pre)/len(pre),3)
                tail = post[-min(8,len(post)):]
                summary["post_mean_luma"] = round(sum(x.luma for x in tail)/len(tail),3)
                summary["theme_changed"] = abs(summary["pre_mean_luma"]-summary["post_mean_luma"]) > 8
            report["theme_toggles"].append(summary)
            write_csv(combined, out / f"theme_{toggle:02d}.csv")
            save_worst(raw, combined, out, f"theme_{toggle:02d}")
            time.sleep(0.25)
    finally:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()

    report["startup_flicker_runs_legacy"] = sum(1 for x in report["startup_runs"] if x.get("flicker_detected"))
    report["startup_endpoint_flicker_runs"] = sum(1 for x in report["startup_runs"] if x.get("endpoint_flicker_detected"))
    report["theme_flicker_toggles_legacy"] = sum(1 for x in report["theme_toggles"] if x.get("flicker_detected"))
    report["theme_endpoint_flicker_toggles"] = sum(1 for x in report["theme_toggles"] if x.get("endpoint_flicker_detected"))
    report["theme_clicks_confirmed"] = sum(1 for x in report["theme_toggles"] if x.get("theme_changed"))

    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    # Prevent a false-green visual test when it never clicked the theme button.
    if report["theme_clicks_confirmed"] < 28:
        raise RuntimeError("Visual test did not activate the actual theme button reliably.")
    if report["startup_endpoint_flicker_runs"] or report["theme_endpoint_flicker_toggles"]:
        raise RuntimeError("Visible flicker or unintended third-state frames detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
