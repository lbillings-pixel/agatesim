import { useEffect, useRef, useState } from "react";

import {
  type Host,
  type QualityBadge,
  type Replica,
  type RunConfig,
  type SpecimenAnalysis,
  type SpecimenFile,
  type SpecimenSettings,
  specimens,
} from "../api";
import { USE_LABEL, adviceFor, levelClass } from "../lib/quality";
import { type Point, type Transect, addMark, distanceTo, project, removeMark, tick } from "../lib/transect";
import { FormClassifier } from "./FormClassifier";
import { ReferenceLabeler } from "./ReferenceLabeler";
import { SpecimenLibrary } from "./SpecimenLibrary";

const MM_PER_INCH = 25.4;
const UP_CHOICES: [number, string][] = [
  [90, "Top of the photo"],
  [270, "Bottom of the photo"],
  [180, "Left of the photo"],
  [0, "Right of the photo"],
];

type Clicking = "ruler" | "seed" | "line" | "marks" | null;

const ZOOMS = [1, 2, 4];
const pct = (x: number | null) => (x === null ? "—" : `${Math.round(100 * x)}%`);
const SNAP_PX = 25; // clicks farther than this from the line are ignored while marking
const SAME_SCREEN_PX = 1.5; // a click this close to a mark repeats it
const REMOVE_SCREEN_PX = 8; // a right-click this close to a mark removes it

interface Props {
  onOpenReplica: (config: RunConfig) => void;
}

const blank: SpecimenSettings = { calibration: null, host: "volcanic", up_deg: 90, seed: null, transects: [] };

/** Specimen photos: a library with quality badges, and per photo: set the
 * scale, analyse, identify forms, fit a replica. */
export function SpecimenWorkbench({ onOpenReplica }: Props) {
  const [tab, setTab] = useState<"library" | "classify" | "references">("library");
  const [quality, setQuality] = useState<QualityBadge[] | null>(null);
  const [files, setFiles] = useState<SpecimenFile[]>([]);
  const [name, setName] = useState<string | null>(null);
  const [settings, setSettings] = useState<SpecimenSettings>(blank);
  const [points, setPoints] = useState<[number, number][]>([]);
  const [distance, setDistance] = useState(1);
  const [unit, setUnit] = useState<"in" | "mm">("in");
  const [faceHeight, setFaceHeight] = useState(0);
  const [clicking, setClicking] = useState<Clicking>(null);
  const [analysis, setAnalysis] = useState<SpecimenAnalysis | null>(null);
  const [replica, setReplica] = useState<Replica | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [noDetail, setNoDetail] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [lineStart, setLineStart] = useState<Point | null>(null);
  const [saved, setSaved] = useState(true);
  const imgRef = useRef<HTMLImageElement>(null);

  const refresh = () => specimens.list().then(setFiles, (e: unknown) => setError(String(e)));
  useEffect(() => {
    refresh();
  }, []);

  const score = (n: string, s: SpecimenSettings) =>
    specimens.quality(n, s).then(
      (r) => setQuality(r.badges),
      () => setQuality(null),
    );

  const choose = (n: string) => {
    setTab("classify");
    setQuality(null);
    setName(n);
    setAnalysis(null);
    setReplica(null);
    setError(null);
    setSize(null);
    setZoom(1);
    setNoDetail(false);
    setActive(null);
    setLineStart(null);
    setSaved(true);
    specimens.settings(n).then((s) => {
      void score(n, s);
      setSettings({ ...s, transects: s.transects ?? [] });
      setActive(s.transects?.length ? 0 : null);
      const c = s.calibration;
      setPoints(c ? [c.p1, c.p2] : []);
      setFaceHeight(c?.face_height_mm ?? 0);
      if (c) {
        setUnit("mm");
        setDistance(c.distance_mm);
      }
    }, () => setSettings(blank));
  };

  const current = (): SpecimenSettings => {
    const [p1, p2] = points;
    const calibration =
      p1 && p2
        ? { p1, p2, distance_mm: unit === "in" ? distance * MM_PER_INCH : distance, face_height_mm: faceHeight }
        : null;
    return { ...settings, calibration };
  };

  const run = async (label: string, action: (s: SpecimenSettings) => Promise<void>) => {
    if (!name) return;
    const s = current();
    setBusy(label);
    setError(null);
    try {
      await specimens.saveSettings(name, s);
      void score(name, s); // the scale and the specimen pick change the scores
      await action(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  // A click in working-image px (the full-resolution detail shown when zoomed in
  // has the same frame), and the photo px per screen px.
  const toPhoto = (e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current;
    if (!img || !size) return null;
    const rect = img.getBoundingClientRect();
    const perScreenPx = size.w / rect.width;
    return { x: (e.clientX - rect.left) * perScreenPx, y: (e.clientY - rect.top) * (size.h / rect.height), perScreenPx };
  };

  const activeLine = () => (active === null ? undefined : settings.transects[active]);

  const updateLine = (updated: Transect) => {
    setSettings({ ...settings, transects: settings.transects.map((l, i) => (i === active ? updated : l)) });
    setSaved(false);
  };

  const onRightClick = (e: React.MouseEvent<HTMLImageElement>) => {
    if (clicking !== "marks") return;
    e.preventDefault();
    const p = toPhoto(e);
    const line = activeLine();
    if (!p || !line) return;
    const updated = removeMark(line, project(line, [p.x, p.y]), REMOVE_SCREEN_PX * p.perScreenPx);
    if (updated !== line) updateLine(updated);
  };

  const onClick = (e: React.MouseEvent<HTMLImageElement>) => {
    const p = toPhoto(e);
    if (!p || !clicking) return;
    const { x, y } = p;
    if (clicking === "line") {
      if (!lineStart) {
        setLineStart([x, y]);
        return;
      }
      const transects = [...settings.transects, { start: lineStart, end: [x, y] as Point, boundaries: [] }];
      setSettings({ ...settings, transects });
      setActive(transects.length - 1);
      setLineStart(null);
      setSaved(false);
      setClicking("marks");
      return;
    }
    if (clicking === "marks") {
      const line = activeLine();
      if (!line || distanceTo(line, [x, y]) > SNAP_PX) return;
      const updated = addMark(line, project(line, [x, y]), SAME_SCREEN_PX * p.perScreenPx);
      if (updated !== line) updateLine(updated);
      return;
    }
    if (clicking === "ruler") {
      const next = points.length >= 2 ? [[x, y] as [number, number]] : [...points, [x, y] as [number, number]];
      setPoints(next);
      if (next.length === 2) setClicking(null);
    } else {
      setSettings({ ...settings, seed: [x, y] });
      setClicking(null);
    }
  };

  const scaleReady = points.length === 2 && distance > 0;

  const tabs = (
    <div className="tabs specimen-tabs" role="tablist" aria-label="Specimens">
      <button type="button" role="tab" aria-selected={tab === "library"} onClick={() => setTab("library")}>
        Library
      </button>
      <button type="button" role="tab" aria-selected={tab === "classify"} onClick={() => setTab("classify")}>
        Classify{name ? `: ${name}` : ""}
      </button>
      <button type="button" role="tab" aria-selected={tab === "references"} onClick={() => setTab("references")}>
        Reference labels
      </button>
    </div>
  );

  if (tab === "references")
    return (
      <div className="specimen-screen">
        {tabs}
        <ReferenceLabeler />
      </div>
    );

  if (tab === "library")
    return (
      <div className="specimen-screen">
        {tabs}
        <SpecimenLibrary
          files={files}
          selected={name}
          onOpen={choose}
          onUploaded={choose}
          onRenamed={(from, to) => {
            if (from === name) setName(to);
          }}
          onDeleted={(n) => {
            if (n === name) {
              setName(null);
              setQuality(null);
            }
          }}
          refresh={() => void refresh()}
        />
      </div>
    );

  return (
    <div className="specimen-screen">
      {tabs}
    <div className="specimens">
      <aside className="specimen-list" aria-label="Specimen photos">
        <h2>Specimens</h2>
        <p className="muted small">
          Photos in your <code>specimens/</code> folder. They stay on this machine and are shown without their metadata.
        </p>
        <ul>
          {files.map((f) => (
            <li key={f.name}>
              <button type="button" className={f.name === name ? "selected" : undefined} onClick={() => choose(f.name)}>
                {f.name}
                {f.has_settings && <span className="muted small"> · scaled</span>}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {name ? (
        <main className="specimen-main">
          <div className="specimen-tools">
            <div className="tool-group">
              <span className="micro-label">Scale</span>
              <button
                type="button"
                className={clicking === "ruler" ? "primary" : undefined}
                onClick={() => {
                  setPoints([]);
                  setClicking("ruler");
                }}
              >
                {points.length === 2 ? "Re-mark ruler" : "Mark two ruler points"}
              </button>
              <label className="inline small">
                apart
                <input
                  id="ruler-distance"
                  type="number"
                  min={0}
                  step={0.1}
                  value={distance}
                  onChange={(e) => setDistance(Number(e.target.value))}
                />
                <select value={unit} onChange={(e) => setUnit(e.target.value as "in" | "mm")}>
                  <option value="in">in</option>
                  <option value="mm">mm</option>
                </select>
              </label>
              <label className="inline small" title="How far the cut face stands above the ruler (e.g. the slab thickness)">
                face above ruler
                <input
                  id="face-height"
                  type="number"
                  min={0}
                  step={0.5}
                  value={faceHeight}
                  onChange={(e) => setFaceHeight(Number(e.target.value))}
                />
                mm
              </label>
            </div>
            <div className="tool-group">
              <label className="inline small">
                <span className="micro-label">Host</span>
                <select value={settings.host} onChange={(e) => setSettings({ ...settings, host: e.target.value as Host })}>
                  <option value="volcanic">Volcanic</option>
                  <option value="sedimentary">Sedimentary</option>
                  <option value="seam">Seam</option>
                </select>
              </label>
              <label className="inline small" title="Which way was up when the agate formed (for horizontal banding)">
                <span className="micro-label">Up was</span>
                <select
                  value={settings.up_deg}
                  onChange={(e) => setSettings({ ...settings, up_deg: Number(e.target.value) })}
                >
                  {UP_CHOICES.map(([deg, label]) => (
                    <option key={deg} value={deg}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={clicking === "seed" ? "primary" : undefined}
                title="If the specimen isn't found, click on it"
                onClick={() => setClicking("seed")}
              >
                {settings.seed ? "Re-pick specimen" : "Pick specimen"}
              </button>
            </div>
            <div className="tool-group">
              <button
                type="button"
                className="primary"
                disabled={!scaleReady || busy !== null}
                onClick={() => run("Analysing", async (s) => setAnalysis(await specimens.analyse(name, s)))}
              >
                Analyse
              </button>
              <button
                type="button"
                disabled={!scaleReady || busy !== null}
                onClick={() => run("Fitting a replica", async (s) => setReplica(await specimens.replicate(name, s)))}
              >
                Replicate
              </button>
              {busy && <span className="muted small">{busy}…</span>}
            </div>
            <div className="tool-group" aria-label="Hand-marked bands">
              <span className="micro-label">Mark bands</span>
              <button
                type="button"
                className={clicking === "line" ? "primary" : undefined}
                onClick={() => {
                  setLineStart(null);
                  setClicking("line");
                }}
              >
                Draw a line
              </button>
              <button
                type="button"
                className={clicking === "marks" ? "primary" : undefined}
                disabled={active === null}
                onClick={() => setClicking(clicking === "marks" ? null : "marks")}
              >
                {clicking === "marks" ? "Stop marking" : "Mark boundaries"}
              </button>
              {settings.transects.length > 1 && (
                <select
                  aria-label="Line to mark"
                  value={active ?? 0}
                  onChange={(e) => setActive(Number(e.target.value))}
                >
                  {settings.transects.map((l, i) => (
                    <option key={i} value={i}>
                      Line {i + 1} ({l.boundaries.length} marks)
                    </option>
                  ))}
                </select>
              )}
              <button
                type="button"
                disabled={active === null}
                onClick={() => {
                  if (active === null) return;
                  if (!confirmDelete) {
                    setConfirmDelete(true); // a second click deletes
                    return;
                  }
                  const transects = settings.transects.filter((_, i) => i !== active);
                  setSettings({ ...settings, transects });
                  setActive(transects.length ? 0 : null);
                  setConfirmDelete(false);
                  setSaved(false);
                }}
                onBlur={() => setConfirmDelete(false)}
              >
                {confirmDelete
                  ? `Click again to delete this line (${settings.transects[active ?? 0]?.boundaries.length ?? 0} marks)`
                  : "Delete line"}
              </button>
              <button
                type="button"
                disabled={saved || busy !== null}
                onClick={() => {
                  if (!name) return;
                  setBusy("Saving marks");
                  specimens
                    .saveSettings(name, current())
                    .then(() => setSaved(true), (e: unknown) => setError(e instanceof Error ? e.message : String(e)))
                    .finally(() => setBusy(null));
                }}
              >
                {saved ? "Marks saved" : "Save marks"}
              </button>
              <label className="inline small">
                Zoom
                <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
                  {ZOOMS.map((z) => (
                    <option key={z} value={z}>
                      {z}×
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          {clicking && (
            <p className="muted small">
              {clicking === "ruler"
                ? `Click ${points.length === 0 ? "the first" : "the second"} point on the ruler.`
                : clicking === "line"
                  ? lineStart
                    ? "Click where the line ends (toward the centre)."
                    : "Click where the line starts: on the outer wall, crossing the bands."
                  : clicking === "marks"
                    ? "Click each boundary between bands along the yellow line; right-click a mark to remove it. Zoom in (full resolution) for fine bands, then Save marks."
                    : "Click on the specimen."}
            </p>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {quality && (
            <section className="specimen-quality" aria-label="Photo quality">
              {quality.map((b) => (
                <div key={b.use}>
                  <span className={levelClass(b.level)}>
                    {USE_LABEL[b.use]}: {b.level}
                  </span>
                  {b.reasons.length > 0 && (
                    <span className="muted small"> {b.reasons.map((r) => r.message).join("; ")}</span>
                  )}
                </div>
              ))}
              {adviceFor(quality).length > 0 && (
                <p className="muted small">Better photos: {adviceFor(quality).join("; ")}.</p>
              )}
            </section>
          )}

          <div className="specimen-views">
            <figure className="photo-view">
              <div className="photo-scroll">
                <div className="photo-frame" style={{ width: `${zoom * 100}%` }}>
                  <img
                    ref={imgRef}
                    src={zoom > 1 && size && !noDetail ? specimens.detailUrl(name) : specimens.photoUrl(name)}
                    alt={`Specimen photo ${name}`}
                    className={clicking ? "clicking" : undefined}
                    onLoad={(e) => {
                      const img = e.currentTarget;
                      if (!size) setSize({ w: img.naturalWidth, h: img.naturalHeight }); // the working image
                    }}
                    onContextMenu={onRightClick}
                    onError={(e) =>
                      e.currentTarget.src.endsWith("/detail")
                        ? setNoDetail(true) // zoom the working image instead
                        : setError(
                        "The photo didn't load. Check the terminal running agatesim for an error, then reload the page.",
                      )
                    }
                    onClick={onClick}
                  />
                  {size && (
                    <svg viewBox={`0 0 ${size.w} ${size.h}`} className="photo-overlay" aria-hidden="true">
                      {analysis && (
                        <polygon points={analysis.outline_px.map(([x, y]) => `${x},${y}`).join(" ")} className="outline" />
                      )}
                      {points.length === 2 && (
                        <line x1={points[0]?.[0]} y1={points[0]?.[1]} x2={points[1]?.[0]} y2={points[1]?.[1]} className="ruler" />
                      )}
                      {points.map(([x, y], i) => (
                        <circle key={i} cx={x} cy={y} r={size.w / 160} className="ruler-point" />
                      ))}
                      {settings.seed && <circle cx={settings.seed[0]} cy={settings.seed[1]} r={size.w / 120} className="seed" />}
                      {settings.transects.map((line, i) => (
                        <g key={i}>
                          <line
                            x1={line.start[0]}
                            y1={line.start[1]}
                            x2={line.end[0]}
                            y2={line.end[1]}
                            className={i === active ? "transect active" : "transect"}
                          />
                          {analysis?.transects[i]?.traced.map((t, j) => {
                            const [a, b] = tick(line, t, size.w / 140);
                            return <line key={`t${j}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="traced" />;
                          })}
                          {analysis?.transects[i]?.edges.map((t, j) => {
                            const [a] = tick(line, t, size.w / 140);
                            const [, b] = tick(line, t, 0);
                            return <line key={`e${j}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="edge" />;
                          })}
                          {line.boundaries.map((t, j) => {
                            const [a, b] = tick(line, t, size.w / 200);
                            return <line key={`m${j}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="mark" />;
                          })}
                        </g>
                      ))}
                      {lineStart && <circle cx={lineStart[0]} cy={lineStart[1]} r={size.w / 250} className="line-start" />}
                    </svg>
                  )}
                </div>
              </div>
              <figcaption className="small">
                {analysis
                  ? `${analysis.size_mm.toFixed(1)} mm across · ${(1000 * analysis.mm_per_px).toFixed(1)} µm per pixel` +
                    (analysis.camera_height_mm ? ` · perspective corrected (camera ≈ ${analysis.camera_height_mm.toFixed(0)} mm up)` : "")
                  : size
                    ? "Mark the scale, then Analyse."
                    : "Loading the photo…"}
              </figcaption>
            </figure>
            {analysis && (
              <figure className="photo-view">
                <img src={analysis.band_map} alt="Bands as traced from the photo" />
                <figcaption className="small">Bands as traced (false colour)</figcaption>
              </figure>
            )}
            {replica && (
              <figure className="photo-view">
                <img src={replica.image} alt="Simulated replica" />
                <figcaption className="small">
                  Replica (growth-history model in this outline) ·{" "}
                  <button type="button" className="link" onClick={() => onOpenReplica(replica.config)}>
                    open in the simulator
                  </button>
                </figcaption>
              </figure>
            )}
          </div>

          <FormClassifier key={name} name={name} />

          {analysis && (
            <section className="criteria-panel">
              <div className="criteria-head">
                <h3>Forms</h3>
                <span className="muted small">
                  A confirmed form is reliable; "not confirmed" says little, since tracing bands from a photo still
                  misses most forms that are there (ADR 0011).
                </span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Form</th>
                    <th>From this photo</th>
                    <th>Criteria passed</th>
                    <th>Measurements</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.identification.map((f) => (
                    <tr key={f.archetype}>
                      <td>{f.archetype}</td>
                      <td>
                        <span className={`pill ${f.verdict === "confirmed" ? "pass" : f.passed ? "pinned" : "na"}`}>{f.verdict}</span>
                      </td>
                      <td className="num">
                        {Math.round(f.score * f.criteria.length)} / {f.criteria.length}
                      </td>
                      <td className="small">
                        {f.criteria
                          .map((c) => `${c.id} ${c.value === null ? "—" : c.value.toPrecision(3)}${c.passed ? " ✓" : ""}`)
                          .join(" · ")}
                      </td>
                    </tr>
                  ))}
                  {Object.entries(analysis.not_from_photos).map(([form, why]) => (
                    <tr key={form}>
                      <td>{form}</td>
                      <td>
                        <span className="pill na">not from photos</span>
                      </td>
                      <td />
                      <td className="small muted">{why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {analysis.transects.length > 0 && (
                <>
                  <h3>Hand-marked bands</h3>
                  <p className="small muted">
                    <span className="legend-mark">yellow</span>: your marks ·{" "}
                    <span className="legend-traced">cyan</span>: boundaries of the traced bands along the same line ·{" "}
                    <span className="legend-edge">orange</span>: boundaries detected at full resolution. A boundary
                    matches a mark within the tolerance shown. Closely spaced marks are easy to hit by chance, so
                    compare the recall with the chance level.
                  </p>
                  <table>
                    <thead>
                      <tr>
                        <th>Line</th>
                        <th>Method</th>
                        <th>Marked</th>
                        <th>Found</th>
                        <th>Matched</th>
                        <th>Recall</th>
                        <th>By chance</th>
                        <th>Precision</th>
                        <th>Mean offset</th>
                        <th>Tolerance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.transects.flatMap(({ score, edge_score }, i) =>
                        (
                          [
                            ["Traced bands", score],
                            ["Full-res edges", edge_score],
                          ] as const
                        ).map(([method, s]) => (
                          <tr key={`${i}${method}`}>
                            <td>{i + 1}</td>
                            <td>{method}</td>
                            <td className="num">{s.marked}</td>
                            <td className="num">{s.traced}</td>
                            <td className="num">{s.matched}</td>
                            <td className="num">{pct(s.recall)}</td>
                            <td className="num">{pct(s.chance_recall)}</td>
                            <td className="num">{pct(s.precision)}</td>
                            <td className="num">{s.mean_offset_mm === null ? "—" : `${s.mean_offset_mm.toFixed(2)} mm`}</td>
                            <td className="num">{s.tolerance_mm.toFixed(2)} mm</td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </>
              )}
              <p className="small muted">
                Bands traced: {analysis.stats.band_count} · median thickness{" "}
                {analysis.stats.thickness_median_mm?.toFixed(2) ?? "—"} mm · open {(100 * analysis.stats.open_fraction).toFixed(0)}%
              </p>
            </section>
          )}
        </main>
      ) : (
        <main className="specimen-main muted">Choose a photo in the Library, or add one there.</main>
      )}
    </div>
    </div>
  );
}
