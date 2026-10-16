import { useState } from "react";

import { exportGif, exportVideo, type FrameSource, saveBlob, videoFormat } from "../lib/animation";

const LENGTHS = [5, 10, 20];

interface Props {
  /** Builds the frames when an export starts (null while there's nothing to export). */
  source: () => FrameSource | null;
  name: string; // file name without extension
}

/** Save the growth animation as an animated GIF or a video. */
export function ExportAnimation({ source, name }: Props) {
  const [seconds, setSeconds] = useState(10);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const video = videoFormat();

  const run = async (kind: "gif" | "video") => {
    const src = source();
    if (!src) return;
    setError(null);
    try {
      const onProgress = (s: number) => setBusy(`${kind === "gif" ? "GIF" : "Video"} ${Math.round(s * 100)}%`);
      setBusy("Starting…");
      if (kind === "gif") {
        saveBlob(await exportGif(src, { seconds, fps: 12, onProgress }), `${name}.gif`);
      } else {
        const { blob, ext } = await exportVideo(src, { seconds, fps: 30, onProgress });
        saveBlob(blob, `${name}.${ext}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="export-animation small">
      <span className="micro-label">Save the growth</span>
      <select aria-label="Animation length" value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} disabled={busy !== null}>
        {LENGTHS.map((s) => (
          <option key={s} value={s}>
            {s} s
          </option>
        ))}
      </select>
      <button type="button" onClick={() => void run("gif")} disabled={busy !== null} title="Animated GIF, 12 frames a second">
        GIF
      </button>
      <button
        type="button"
        onClick={() => void run("video")}
        disabled={busy !== null || video === null}
        title={video ? `${video.ext.toUpperCase()} video, 30 frames a second (recorded in real time)` : "This browser can't record video"}
      >
        Video{video ? ` (${video.ext.toUpperCase()})` : ""}
      </button>
      {busy && <span className="muted" aria-live="polite">{busy}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  );
}
