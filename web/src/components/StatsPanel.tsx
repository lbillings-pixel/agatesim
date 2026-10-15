import type { BandStats } from "../api";

type Row = { label: string; value: (s: BandStats) => number | null; format: (v: number) => string };

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const mm = (v: number) => `${v.toFixed(3)} mm`;
const plain = (digits: number) => (v: number) => v.toFixed(digits);

const ROWS: Row[] = [
  { label: "Bands", value: (s) => s.band_count, format: plain(0) },
  { label: "Mean band thickness", value: (s) => s.thickness_mean_mm, format: mm },
  { label: "Median band thickness", value: (s) => s.thickness_median_mm, format: mm },
  { label: "Thickness variation (CV)", value: (s) => s.thickness_cv, format: plain(2) },
  { label: "Translucency contrast", value: (s) => s.translucency_contrast, format: plain(2) },
  { label: "Mean iron staining", value: (s) => s.iron_mean, format: plain(2) },
  { label: "Chalcedony", value: (s) => s.chalcedony_fraction, format: pct },
  { label: "Quartz", value: (s) => s.quartz_fraction, format: pct },
  { label: "Open space", value: (s) => s.open_fraction, format: pct },
  { label: "Quartz crystals", value: (s) => s.crystal_count, format: plain(0) },
];

interface Column {
  title: string;
  stats: BandStats | null;
}

export function StatsPanel({ columns }: { columns: Column[] }) {
  const shown = columns.filter((c): c is { title: string; stats: BandStats } => c.stats !== null);
  if (shown.length === 0) return null;
  return (
    <section className="criteria-panel">
      <h3>Band statistics</h3>
      <table>
        <thead>
          <tr>
            <th scope="col">Measure</th>
            {shown.map((c) => (
              <th key={c.title} scope="col" className="num">
                {c.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              {shown.map((c) => {
                const v = r.value(c.stats);
                return (
                  <td key={c.title} className="num">
                    {v === null ? "—" : r.format(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Thickness is measured along 48 lines running inward from the wall. The same measures will
        describe specimen photos.
      </p>
    </section>
  );
}
