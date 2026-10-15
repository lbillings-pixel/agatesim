import { useEffect, useRef, useState } from "react";

import {
  type Host,
  type Replica,
  type RunConfig,
  type SpecimenAnalysis,
  type SpecimenFile,
  type SpecimenSettings,
  specimens,
} from "../api";

const MM_PER_INCH = 25.4;
const UP_CHOICES: [number, string][] = [
  [90, "Top of the photo"],
  [270, "Bottom of the photo"],
  [180, "Left of the photo"],
  [0, "Right of the photo"],
];

type Clicking = "ruler" | "seed" | null;

interface Props {
  onOpenReplica: (config: RunConfig) => void;
}

const blank: SpecimenSettings = { calibration: null, host: "volcanic", up_deg: 90, seed: null };

/** Specimen photos: set the scale, analyse, identify forms, fit a replica. */
export function SpecimenWorkbench({ onOpenReplica }: Props) {
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
  const imgRef = useRef<HTMLImageElement>(null);

  const refresh = () => specimens.list().then(setFiles, (e: unknown) => setError(String(e)));
  useEffect(() => {
    refresh();
  }, []);

  const choose = (n: string) => {
    setName(n);
    setAnalysis(null);
    setReplica(null);
    setError(null);
    setSize(null);
    specimens.settings(n).then((s) => {
      setSettings(s);
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
      await action(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const onClick = (e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current;
    if (!img || !clicking) return;
    const rect = img.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * img.naturalWidth;
    const y = ((e.clientY - rect.top) / rect.height) * img.naturalHeight;
    if (clicking === "ruler") {
      const next = points.length >= 2 ? [[x, y] as [number, number]] : [...points, [x, y] as [number, number]];
      setPoints(next);
      if (next.length === 2) setClicking(null);
    } else {
      setSettings({ ...settings, seed: [x, y] });
      setClicking(null);
    }
  };

  const upload = (file: File | undefined) => {
    if (!file) return;
    setBusy("Uploading");
    specimens
      .upload(file)
      .then((r) => {
        refresh();
        choose(r.name);
      }, (e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(null));
  };

  const scaleReady = points.length === 2 && distance > 0;

  return (
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
        <label className="upload">
          <span className="micro-label">Add a photo</span>
          <input type="file" accept="image/jpeg,image/png" onChange={(e) => upload(e.target.files?.[0])} />
        </label>
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
          </div>
          {clicking && (
            <p className="muted small">
              {clicking === "ruler"
                ? `Click ${points.length === 0 ? "the first" : "the second"} point on the ruler.`
                : "Click on the specimen."}
            </p>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          <div className="specimen-views">
            <figure className="photo-view">
              <div className="photo-frame">
                <img
                  ref={imgRef}
                  src={specimens.photoUrl(name)}
                  alt={`Specimen photo ${name}`}
                  className={clicking ? "clicking" : undefined}
                  onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
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
                  </svg>
                )}
              </div>
              <figcaption className="small">
                {analysis
                  ? `${analysis.size_mm.toFixed(1)} mm across · ${(1000 * analysis.mm_per_px).toFixed(1)} µm per pixel` +
                    (analysis.camera_height_mm ? ` · perspective corrected (camera ≈ ${analysis.camera_height_mm.toFixed(0)} mm up)` : "")
                  : "Mark the scale, then Analyse."}
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
              <p className="small muted">
                Bands traced: {analysis.stats.band_count} · median thickness{" "}
                {analysis.stats.thickness_median_mm?.toFixed(2) ?? "—"} mm · open {(100 * analysis.stats.open_fraction).toFixed(0)}%
              </p>
            </section>
          )}
        </main>
      ) : (
        <main className="specimen-main muted">Choose a photo, or add one.</main>
      )}
    </div>
  );
}
