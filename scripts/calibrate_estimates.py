"""Check the caution badge's estimates against real runs (ADR 0060).

Each scenario runs in its own process; its time and peak memory (Windows'
process counters) are printed beside agatesim.estimate's prediction. Re-run after
a model's cost changes and adjust the constants in agatesim.estimate.

    uv run --no-sync python scripts/calibrate_estimates.py [preset or kind ...]
"""
# pyright: basic
# ruff: noqa: E501  (the child script is kept as one readable block)

import json
import subprocess
import sys

CHILD = r"""
import ctypes, json, sys, time, tempfile, datetime
from ctypes import wintypes
from pathlib import Path
class C(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("f", wintypes.DWORD), ("peak", ctypes.c_size_t), ("ws", ctypes.c_size_t)] + [(f"x{i}", ctypes.c_size_t) for i in range(6)]
k = ctypes.WinDLL("kernel32"); k.GetCurrentProcess.restype = wintypes.HANDLE
k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(C), wintypes.DWORD]
def peak():
    c = C(); c.cb = ctypes.sizeof(c); k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb); return c.peak / 1e9
kind, name, res, extra = sys.argv[1], sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4])
from agatesim import estimate
if kind == "run2d":
    from agatesim.config import load_preset
    from agatesim.simulate import simulate
    from agatesim.runs import write_run
    config = load_preset(name).with_resolution(res)
    if extra:
        config = config.model_copy(update={"model": type(config.model).model_validate({**config.model.model_dump(mode="json"), **extra})})
    est = estimate.run_2d(config, res)
    t = time.perf_counter()
    with tempfile.TemporaryDirectory() as d:
        write_run(simulate(config), Path(d), started=datetime.datetime.now().astimezone(), elapsed_s=0.0)
else:
    from agatesim.volume.config import load_volume_preset, SliceConfig
    from agatesim.volume.simulate import prepare_volume
    from agatesim.volume.survey import survey
    config = load_volume_preset(name)
    if extra.get("model"):
        config = config.model_copy(update={"model": type(config.model).model_validate({**config.model.model_dump(mode="json"), **extra["model"]})})
    if kind == "view3d":
        est = estimate.view_3d(config, res, 384)
        t = time.perf_counter()
        sim = prepare_volume(config); sim.volume(res); sim.cut(SliceConfig(resolution=384))
    elif kind == "survey3d":
        est = estimate.survey_3d(config, extra["cuts"], res)
        t = time.perf_counter()
        survey(prepare_volume(config), extra["cuts"], res)
    else:  # run3d
        from agatesim.volume.runs import write_volume_run
        config = config.with_resolution(res)
        est = estimate.run_3d(config, res, extra.get("cuts", 0), 512)
        t = time.perf_counter()
        sim = prepare_volume(config)
        found = survey(sim, extra["cuts"], 512) if extra.get("cuts") else None
        out = Path("runs/_calibrate"); out.mkdir(parents=True, exist_ok=True)
        path, _ = write_volume_run(sim, out, started=datetime.datetime.now().astimezone(), elapsed_s=0.0, survey=found)
        import shutil; shutil.rmtree(out)
print(json.dumps({"s": time.perf_counter() - t, "peak_gb": peak(), "est_s": est.seconds, "est_gb": est.memory_gb, "heavy": est.heavy}))
"""

SCENARIOS = [
    ("run2d", "fortification", 1024, {}),
    ("run2d", "fortification", 2048, {}),
    ("run2d", "stick", 2048, {}),
    ("run2d", "moss", 2048, {}),
    ("run2d", "eye-mechanistic", 1024, {}),
    ("run2d", "fortification-mechanistic", 2048, {}),
    ("run2d", "fortification-mechanistic", 256, {"rejection": 2.0}),
    ("run2d", "fortification-mechanistic", 256, {"rejection": 3.0}),
    ("run2d", "fortification-mechanistic", 256, {"rejection": 4.0}),
    ("run2d", "fortification-mechanistic", 256, {"rejection": 5.0}),
    ("run2d", "fortification-mechanistic", 256, {"trapping_velocity": 1.5}),
    ("run2d", "fortification-mechanistic", 256, {"trapping_velocity": 2.3}),
    ("run2d", "fortification-mechanistic", 256, {"trapping_velocity": 3.12}),
    ("run2d", "fortification-mechanistic", 256, {"rejection": 3.0, "trapping_velocity": 2.3}),
    ("run2d", "liesegang-nodule", 512, {}),
    ("run2d", "liesegang-nodule", 512, {"lattice_mm": 0.035}),
    ("view3d", "moss-3d", 96, {}),
    ("view3d", "moss-fine-3d", 96, {}),
    ("view3d", "plume-3d", 96, {}),
    ("view3d", "liesegang-nodule-3d", 96, {}),
    ("survey3d", "fortification-mechanistic-3d", 512, {"cuts": 40}),
    ("survey3d", "stick-mechanistic-3d", 768, {"cuts": 20}),
    ("run3d", "fortification-mechanistic-3d", 256, {"cuts": 0}),
    ("run3d", "moss-3d", 192, {"cuts": 40}),
]

only = sys.argv[1:]
for kind, name, res, extra in SCENARIOS:
    if only and name not in only and kind not in only:
        continue
    out = subprocess.run(
        [sys.executable, "-c", CHILD, kind, name, str(res), json.dumps(extra)],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if out.returncode:
        print(
            f"{kind:8s} {name:28s} {res:5d} {extra}: FAILED {out.stderr.strip().splitlines()[-1][:120]}",
            flush=True,
        )
        continue
    r = json.loads(out.stdout.strip().splitlines()[-1])
    print(
        f"{kind:8s} {name:28s} {res:5d} {json.dumps(extra):40s} actual {r['s']:7.1f}s {r['peak_gb']:5.2f}GB | "
        f"estimate {r['est_s']:7.1f}s {r['est_gb']:5.2f}GB heavy={r['heavy']}",
        flush=True,
    )
