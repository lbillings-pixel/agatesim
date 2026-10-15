import type { Schedule, ScheduledVariable, ScheduleEvent } from "../api";
import { newEvent, problems, sample } from "../lib/schedule";
import type { Control } from "../lib/schema";
import { Slider } from "./ParamPanel";

const T = Array.from({ length: 201 }, (_, i) => i / 200);
const W = 300;
const H = 64;

const FIELDS: Record<ScheduleEvent["type"], { key: string; label: string; time: boolean }[]> = {
  step: [
    { key: "at", label: "at", time: true },
    { key: "value", label: "to", time: false },
  ],
  ramp: [
    { key: "start", label: "from", time: true },
    { key: "end", label: "until", time: true },
    { key: "value", label: "to", time: false },
  ],
  pulse: [
    { key: "at", label: "at", time: true },
    { key: "width", label: "for", time: true },
    { key: "value", label: "value", time: false },
  ],
};

interface Props {
  variable: ScheduledVariable;
  schedule: Schedule;
  onChange: (schedule: Schedule) => void;
}

export function ScheduleEditor({ variable, schedule, onChange }: Props) {
  const { min, max } = variable;
  const values = sample(schedule, T);
  const y = (v: number) => H - 4 - ((v - min) / (max - min || 1)) * (H - 8);
  const line = values.map((v, i) => `${(T[i] ?? 0) * W},${y(v).toFixed(2)}`).join(" ");
  const area = `0,${H} ${line} ${W},${H}`;

  const base: Control = {
    key: "base", label: "Starts at", units: "", nature: variable.nature,
    description: "", min, max, step: 0.01, defaultValue: variable.default.base,
  };

  const setEvent = (i: number, event: ScheduleEvent) =>
    onChange({ ...schedule, events: schedule.events.map((e, j) => (j === i ? event : e)) });

  return (
    <div className="schedule">
      <div className="param-head">
        <span className="schedule-title" title={variable.description}>{variable.label}</span>
        <span className={`nature nature-${variable.nature}`}>{variable.nature}</span>
      </div>
      <p className="param-help">{variable.description}</p>
      <svg
        className="schedule-plot"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${variable.label} over formation time`}
      >
        <line x1={W / 2} x2={W / 2} y1={0} y2={H} className="grid" />
        <polygon points={area} className="area" />
        <polyline points={line} className="curve" />
      </svg>
      <div className="schedule-axis small muted">
        <span>start</span>
        <span>formation time</span>
        <span>end</span>
      </div>
      <Slider
        id={`schedule-${variable.key}-base`}
        control={base}
        value={schedule.base}
        onChange={(v) => onChange({ ...schedule, base: v })}
      />
      {schedule.events.map((event, i) => {
        const issues = problems(event);
        return (
          <div key={i} className="event">
            <span className="event-type">{event.type}</span>
            {FIELDS[event.type].map((f) => {
              const id = `schedule-${variable.key}-${i}-${f.key}`;
              const current = (event as unknown as Record<string, number>)[f.key] ?? 0;
              return (
                <label key={f.key} htmlFor={id} className="event-field">
                  <span>{f.label}</span>
                  <input
                    id={id}
                    type="number"
                    step={0.01}
                    min={f.time ? 0 : min}
                    max={f.time ? 1 : max}
                    value={current}
                    onChange={(e) => setEvent(i, { ...event, [f.key]: Number(e.target.value) } as ScheduleEvent)}
                  />
                </label>
              );
            })}
            <button
              type="button"
              className="icon"
              aria-label={`Remove ${event.type}`}
              onClick={() => onChange({ ...schedule, events: schedule.events.filter((_, j) => j !== i) })}
            >
              ×
            </button>
            {issues.length > 0 && <p className="event-problem">{issues.join(" ")}</p>}
          </div>
        );
      })}
      <div className="event-add">
        {(["step", "ramp", "pulse"] as const).map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => onChange({ ...schedule, events: [...schedule.events, newEvent(type, min, max)] })}
          >
            + {type}
          </button>
        ))}
      </div>
    </div>
  );
}
