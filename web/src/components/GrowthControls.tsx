import { useEffect, useRef, useState } from "react";

import { advanceGrowth, SPEEDS } from "../lib/growth";

// Longest step taken for one frame: slow frames still play at speed, but a tab
// left in the background doesn't jump ahead when it returns.
const MAX_FRAME_SECONDS = 0.5;

interface Props {
  id: string;
  value: number; // 0..1, share of formation time shown
  onChange: (value: number) => void;
}

/** The growth slider with playback: play or pause, speed and looping, so fast or
 * slow stages of growth can be watched at a comfortable pace. */
export function GrowthControls({ id, value, onChange }: Props) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [loop, setLoop] = useState(false);
  // The latest value and callbacks, for the animation loop.
  const latest = useRef({ value, onChange, speed, loop });
  useEffect(() => {
    latest.current = { value, onChange, speed, loop };
  });

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const { value: t, onChange: set, speed: s, loop: l } = latest.current;
      const step = advanceGrowth(t, Math.min((now - last) / 1000, MAX_FRAME_SECONDS), s, l);
      last = now;
      set(step.t);
      if (step.playing) frame = requestAnimationFrame(tick);
      else setPlaying(false);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const play = () => {
    if (!playing && value >= 1) onChange(0); // replay from the start
    setPlaying(!playing);
  };

  return (
    <div className="growth">
      <button
        type="button"
        className="play"
        onClick={play}
        aria-label={playing ? "Pause the growth" : "Play the growth"}
        title={playing ? "Pause" : "Play the agate forming"}
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <label htmlFor={`growth-${id}`}>Growth</label>
      <input
        id={`growth-${id}`}
        type="range"
        min={0}
        max={1}
        step={0.005}
        value={value}
        onChange={(e) => {
          setPlaying(false);
          onChange(Number(e.target.value));
        }}
      />
      <output htmlFor={`growth-${id}`}>{Math.round(value * 100)}%</output>
      <select
        aria-label="Playback speed"
        value={speed}
        onChange={(e) => setSpeed(Number(e.target.value))}
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>
      <label className="inline small" title="Start again at the end">
        <input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} /> Loop
      </label>
    </div>
  );
}
