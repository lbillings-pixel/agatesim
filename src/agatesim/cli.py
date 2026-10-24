"""Command-line interface: `agatesim ...`."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agatesim import __version__
from agatesim.archetypes import load_registry, to_markdown

if TYPE_CHECKING:
    from agatesim.volume.config import VolumeConfig

PREVIEW_RESOLUTION = 256


def _cmd_archetypes(args: argparse.Namespace) -> int:
    registry = load_registry()
    if args.write is not None:
        path: Path = args.write
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(registry), encoding="utf-8", newline="\n")
        print(f"wrote {path}")
        return 0
    print(f"{'rung':>4}  {'procedural':<12} {'mechanistic':<12} {'archetype':<24} subsystem")
    for a in registry.by_rung():
        deps = f"  (needs {', '.join(a.depends_on)})" if a.depends_on else ""
        print(
            f"{a.rung:>4}  {a.status.procedural.value:<12} {a.status.mechanistic.value:<12} "
            f"{a.id:<24} {a.subsystem.value}{deps}"
        )
    return 0


def _cmd_cavities(_: argparse.Namespace) -> int:
    from agatesim.geometry import CAVITY_PRESETS

    for p in CAVITY_PRESETS.values():
        print(f"{p.name:<18} {p.host.value:<12} {p.description}")
    return 0


def _cmd_presets(_: argparse.Namespace) -> int:
    from agatesim.config import load_preset, preset_names

    for name in preset_names():
        c = load_preset(name)
        print(f"{name:<16} {c.model.kind:<26} cavity={c.cavity.label}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from agatesim.config import load_config, load_preset
    from agatesim.runs import write_run
    from agatesim.simulate import simulate

    source = Path(args.config)
    config = load_config(source) if source.suffix == ".toml" else load_preset(args.config)
    if args.preview:
        config = config.with_resolution(PREVIEW_RESOLUTION)
    if args.resolution is not None:
        config = config.with_resolution(args.resolution)

    started = datetime.now().astimezone()
    t0 = time.perf_counter()
    result = simulate(config)
    record = write_run(result, args.out, started=started, elapsed_s=time.perf_counter() - t0)
    print(f"run written to {record.path}")
    if record.evaluation is None:
        return 0
    ev = record.evaluation
    for r in ev.results:
        mark = "PASS" if r.passed else "FAIL"
        value = "n/a" if r.value is None else f"{r.value:.4g}"
        print(f"  {mark}  {r.id:<22} {value:>10}  {r.detail}")
    print(f"{ev.archetype}: {'PASSED' if ev.passed else 'FAILED'}")
    return 0 if ev.passed or not args.check else 1


VOLUME_PREVIEW_RESOLUTION = 96


def _volume_config(args: argparse.Namespace) -> VolumeConfig:
    from agatesim.volume.config import load_volume_config, load_volume_preset

    source = Path(args.config)
    config = (
        load_volume_config(source) if source.suffix == ".toml" else load_volume_preset(args.config)
    )
    if args.preview:
        config = config.with_resolution(VOLUME_PREVIEW_RESOLUTION)
    if args.resolution is not None:
        config = config.with_resolution(args.resolution)
    return config


def _print_survey(summary: dict[str, object]) -> None:
    print(f"  {summary['judged']} of {summary['cuts']} random cuts judged")
    rate = summary["pass_rate"]
    if rate is not None:
        print(f"  pass rate {rate:.0%}")
        criteria = summary["criteria"]
        assert isinstance(criteria, dict)
        for cid, r in criteria.items():  # pyright: ignore[reportUnknownVariableType]
            print(f"    {cid!s:<22} {'n/a' if r is None else f'{r:.0%}'}")
    ratio = summary.get("apparent_over_true")
    if isinstance(ratio, dict):
        print(
            f"  apparent / true band thickness: median {ratio['median']:.2f} "
            f"(quartiles {ratio['q25']:.2f}-{ratio['q75']:.2f})"
        )


def _cmd_volume_run(args: argparse.Namespace) -> int:
    from agatesim.volume.runs import write_volume_run
    from agatesim.volume.simulate import prepare_volume
    from agatesim.volume.survey import survey

    config = _volume_config(args)
    started = datetime.now().astimezone()
    t0 = time.perf_counter()
    sim = prepare_volume(config)
    found = survey(sim, args.survey, args.cut_resolution, seed=config.seed) if args.survey else None
    path, ev = write_volume_run(
        sim, args.out, started=started, elapsed_s=time.perf_counter() - t0, survey=found
    )
    print(f"run written to {path}")
    if found is not None:
        _print_survey(found.summary())
    if ev is None:
        return 0
    for r in ev.results:
        mark = "PASS" if r.passed else "FAIL"
        value = "n/a" if r.value is None else f"{r.value:.4g}"
        print(f"  {mark}  {r.id:<22} {value:>10}  {r.detail}")
    print(f"{ev.archetype} (configured cut): {'PASSED' if ev.passed else 'FAILED'}")
    return 0 if ev.passed or not args.check else 1


def _cmd_volume_survey(args: argparse.Namespace) -> int:
    import json

    from agatesim.volume.simulate import prepare_volume
    from agatesim.volume.survey import survey

    config = _volume_config(args)
    found = survey(prepare_volume(config), args.cuts, args.cut_resolution, seed=args.seed)
    if args.json is not None:
        path: Path = args.json
        path.write_text(json.dumps(found.to_json(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    print(f"{config.name}:")
    _print_survey(found.summary())
    return 0


def _cmd_volume_presets(_: argparse.Namespace) -> int:
    from agatesim.volume.config import load_volume_preset, volume_preset_names

    for name in volume_preset_names():
        c = load_volume_preset(name)
        print(f"{name:<40} {c.model.kind:<26} solid={c.solid.label}")
    return 0


def _cmd_volume_solids(_: argparse.Namespace) -> int:
    from agatesim.volume.solids import SOLID_PRESETS

    for p in SOLID_PRESETS.values():
        print(f"{p.name:<18} {p.host.value:<12} {p.description}")
    return 0


def _add_volume(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    vol = sub.add_parser("volume", help="3D runs: cavities as solids, judged on cuts")
    vsub = vol.add_subparsers(dest="volume_command", required=True)

    def source(p: argparse.ArgumentParser) -> None:
        p.add_argument("config", help="3D preset name (see `agatesim volume presets`) or a .toml")
        p.add_argument(
            "--preview", action="store_true", help=f"{VOLUME_PREVIEW_RESOLUTION}³ voxels"
        )
        p.add_argument("--resolution", type=int, help="voxels along the longest side")
        p.add_argument("--cut-resolution", type=int, default=512, help="pixels per surveyed cut")

    p = vsub.add_parser("run", help="run a 3D simulation and write its record")
    source(p)
    p.add_argument("--out", type=Path, default=Path("runs"), help="runs directory (default: runs)")
    p.add_argument("--survey", type=int, default=0, metavar="N", help="also judge N random cuts")
    p.add_argument("--check", action="store_true", help="exit 1 if the configured cut fails")
    p.set_defaults(func=_cmd_volume_run)

    p = vsub.add_parser("survey", help="judge random cuts through a 3D run")
    source(p)
    p.add_argument("--cuts", type=int, default=60)
    p.add_argument("--seed", type=int, default=0, help="seed for the cut planes")
    p.add_argument("--json", type=Path, metavar="PATH", help="write every cut to a JSON file")
    p.set_defaults(func=_cmd_volume_survey)

    p = vsub.add_parser("presets", help="list the shipped 3D presets")
    p.set_defaults(func=_cmd_volume_presets)

    p = vsub.add_parser("solids", help="list the preset 3D cavity shapes")
    p.set_defaults(func=_cmd_volume_solids)


def _cmd_library(args: argparse.Namespace) -> int:
    from agatesim import library

    if args.library_command == "hold-out":
        from agatesim import taps

        test = taps.choose_test_set(library.load_labels(), n=args.n)
        taps.write_test_set(test)
        print(f"held out {len(test)} photos for tap testing in {taps.TAPS_TOML}")
        return 0
    lib = library.load_library()
    if args.library_command == "fetch":
        n, size = library.fetch(lib, limit=args.limit)
        print(f"fetched {n} images ({size / 1e6:.0f} MB) into {library.IMAGES_DIR}")
    have = sum(i.path.exists() for i in lib.images)
    labels = library.load_labels()
    print(f"{len(lib.images)} in the list, {have} fetched, {len(labels)} labelled")
    return 0


def _add_library(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    lib = sub.add_parser("library", help="the reference library of open-licence photos")
    lsub = lib.add_subparsers(dest="library_command", required=True)
    p = lsub.add_parser("fetch", help="download listed images not yet on disk")
    p.add_argument("--limit", type=int, help="at most this many")
    p.set_defaults(func=_cmd_library)
    p = lsub.add_parser("status", help="how many are listed, fetched and labelled")
    p.set_defaults(func=_cmd_library)
    p = lsub.add_parser("hold-out", help="choose the photos held out for tap testing (ADR 0068)")
    p.add_argument("--n", type=int, default=40, help="how many (default 40)")
    p.set_defaults(func=_cmd_library)


def _cmd_classify(args: argparse.Namespace) -> int:
    from agatesim import classify

    if args.classify_command == "fetch":
        got = classify.fetch_model()
        print(f"{'fetched' if got else 'already have'} {classify.MODEL_PATH}")
        return 0
    embedder = classify.OnnxEmbedder()
    if args.classify_command == "photo":
        from agatesim.specimen.photo import load_photo

        model = classify.Classifier.load()
        a = classify.answer(model, embedder.embed(load_photo(args.path.read_bytes(), 1024).rgb))
        print("undetermined" if a.undetermined else "likely: " + ", ".join(f for f, _ in a.likely))
        for form, p in a.ranked[:5]:
            print(f"  {form:24s} {p:4.0%}")
        return 0
    own = args.specimens if args.specimens.is_dir() else None
    real, sims, forms = classify.gather(embedder, own)
    if args.classify_command == "evaluate":
        ev = classify.cross_validate(real, sims, forms)
        print(f"{ev.photos} labelled photos, held out in 5 folds")
        print(f"most likely form among the labels: {ev.top_hit:.0%}")
        print(f"every reported form right: {ev.all_right:.0%}")
        print(f"undetermined: {ev.undetermined:.0%}")
        for f in ev.forms:
            print(f"  {f.form:24s} found {f.correct}/{f.photos}, right {f.correct}/{f.reported}")
        return 0
    model = classify.train(real + sims, forms, embedder.key)
    model.save()
    print(f"trained on {len(real)} labelled photos and {len(sims)} simulated slabs")
    print(f"saved {classify.CLASSIFIER_PATH}")
    return 0


def _add_classify(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    cls = sub.add_parser("classify", help="the learned form classifier (ADR 0067)")
    csub = cls.add_subparsers(dest="classify_command", required=True)
    p = csub.add_parser("fetch", help="download the image model (84 MB, once)")
    p.set_defaults(func=_cmd_classify)
    for name, text in (
        ("train", "train on the labels and simulated slabs"),
        ("evaluate", "held-out results on the labelled photos"),
    ):
        p = csub.add_parser(name, help=text)
        p.add_argument(
            "--specimens",
            type=Path,
            default=Path("specimens"),
            help="also the owner's labels of their own photos here (default: specimens)",
        )
        p.set_defaults(func=_cmd_classify)
    p = csub.add_parser("photo", help="classify one photo")
    p.add_argument("path", type=Path)
    p.set_defaults(func=_cmd_classify)


def _cmd_serve(args: argparse.Namespace) -> int:
    import threading
    import webbrowser

    import uvicorn

    from agatesim.server.app import STATIC_DIR, create_app

    if not (STATIC_DIR / "index.html").exists():
        print(
            "The web UI isn't built yet. Build it once with:\n  npm --prefix web ci\n"
            "  npm --prefix web run build\nThe API is still served under /api."
        )
    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    print(f"agatesim UI at {url} (runs saved to {args.runs.resolve()}); Ctrl+C to stop")
    uvicorn.run(
        create_app(args.runs, specimens_dir=args.specimens),
        host=args.host,
        port=args.port,
        log_level="warning",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agatesim", description=__doc__)
    parser.add_argument("--version", action="version", version=f"agatesim {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("archetypes", help="list the archetype ladder")
    p.add_argument("--write", type=Path, metavar="PATH", help="write the ladder as markdown")
    p.set_defaults(func=_cmd_archetypes)

    p = sub.add_parser("cavities", help="list the preset cavity shapes")
    p.set_defaults(func=_cmd_cavities)

    p = sub.add_parser("presets", help="list the shipped run presets")
    p.set_defaults(func=_cmd_presets)

    p = sub.add_parser("run", help="run a simulation from a preset name or a config .toml")
    p.add_argument("config", help="preset name (see `agatesim presets`) or path to a .toml")
    p.add_argument("--out", type=Path, default=Path("runs"), help="runs directory (default: runs)")
    p.add_argument("--preview", action="store_true", help=f"{PREVIEW_RESOLUTION}px quick preview")
    p.add_argument("--resolution", type=int, help="override grid resolution")
    p.add_argument("--check", action="store_true", help="exit 1 if archetype criteria fail")
    p.set_defaults(func=_cmd_run)

    _add_volume(sub)
    _add_library(sub)
    _add_classify(sub)

    p = sub.add_parser("serve", help="start the local web app")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost only)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--runs", type=Path, default=Path("runs"), help="runs directory")
    p.add_argument(
        "--specimens",
        type=Path,
        default=Path("specimens"),
        help="folder of specimen photos (stays on this machine)",
    )
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    p.set_defaults(func=_cmd_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
