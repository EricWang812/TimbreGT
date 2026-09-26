import { useEffect, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";

// Demo-only view of template adaptation (§7.4). Data comes from `make drift`
// (web/public/drift/results.json, gitignored), computed on TORGO recordings.
const RESULTS_URL = "/drift/results.json";
const pct = (x) => (x == null ? "n/a" : `${(x * 100).toFixed(1)}%`);

const W = 640, H = 300, PAD = { l: 56, r: 16, t: 16, b: 48 };

function DriftChart({ bins }) {
  const n = bins.static.length;
  const x = (i) => PAD.l + (i * (W - PAD.l - PAD.r)) / Math.max(1, n - 1);
  const y = (v) => PAD.t + (1 - v) * (H - PAD.t - PAD.b);
  const line = (values) => values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="drift-chart" role="img"
      aria-label="Share of the speaker's own takes accepted, over time, with and without adaptation. The table below has the same numbers.">
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="drift-grid" />
          <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" className="drift-axis">{v * 100}%</text>
        </g>
      ))}
      {bins.static.map((_, i) => (
        <text key={i} x={x(i)} y={H - PAD.b + 20} textAnchor="middle" className="drift-axis">{i + 1}</text>
      ))}
      <text x={(PAD.l + W - PAD.r) / 2} y={H - 6} textAnchor="middle" className="drift-axis">Later takes, in recording order (sixths)</text>
      <polyline points={line(bins.static)} className="drift-line drift-static" />
      <polyline points={line(bins.adaptive)} className="drift-line drift-adaptive" />
      {bins.static.map((v, i) => v != null && <rect key={`s${i}`} x={x(i) - 5} y={y(v) - 5} width="10" height="10" className="drift-static-mark" />)}
      {bins.adaptive.map((v, i) => v != null && <circle key={`a${i}`} cx={x(i)} cy={y(v)} r="6" className="drift-adaptive-mark" />)}
    </svg>
  );
}

export default function Dashboard() {
  const [state, setState] = useState({ status: "loading" });
  const [group, setGroup] = useState("all");

  useEffect(() => {
    let cancelled = false;
    fetch(RESULTS_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(
        (data) => !cancelled && setState({ status: "ready", data }),
        (err) => {
          console.error("drift results failed to load", err);
          if (!cancelled) setState({ status: "error" });
        },
      );
    return () => { cancelled = true; };
  }, []);

  if (state.status === "loading") return <p aria-busy="true">Loading the adaptation results…</p>;
  if (state.status === "error") {
    return (
      <div className="stack">
        <PageHeading>Voice changes over time</PageHeading>
        <p className="message-error" role="alert">
          No adaptation results on this machine yet. Run <code>make eval</code>, then <code>make drift</code>, and reload.
        </p>
      </div>
    );
  }

  const { data } = state;
  const bins = data.accept_by_bin[group];
  const speakers = data.series.filter((s) => group === "all" || s.group === group);
  return (
    <div className="stack drift">
      <PageHeading>Voice changes over time</PageHeading>
      <p>
        A voice enrolled once can drift away from its template, and a condition such as ALS can change it month to
        month. After each confident approval, Timbre moves the template slightly toward the new take
        ({Math.round(data.alpha * 100)}% of the way), never more than a fixed limit per update. Below, the same later
        recordings are checked against a template that adapts and one that stays as enrolled.
      </p>

      <section className="panel stack" aria-labelledby="drift-chart-title">
        <h2 id="drift-chart-title">Own takes accepted, with and without adaptation</h2>
        <fieldset className="drift-filter">
          <legend>Speakers</legend>
          {[["all", "All"], ["dysarthric", "With dysarthria"], ["control", "Control"]].map(([value, label]) => (
            <label key={value}>
              <input type="radio" name="drift-group" value={value} checked={group === value}
                onChange={() => setGroup(value)} disabled={!data.accept_by_bin[value].static.some((v) => v != null)} />
              {label}
            </label>
          ))}
        </fieldset>
        <ul className="drift-legend">
          <li><svg width="24" height="14" aria-hidden="true"><circle cx="12" cy="7" r="6" className="drift-adaptive-mark" /></svg> Adaptive template (solid line)</li>
          <li><svg width="24" height="14" aria-hidden="true"><rect x="7" y="2" width="10" height="10" className="drift-static-mark" /></svg> Static template (dashed line)</li>
        </ul>
        <DriftChart bins={bins} />
        <table className="summary">
          <caption>Share of own takes accepted, by sixth of the later recordings ({speakers.length} speakers)</caption>
          <thead>
            <tr><th scope="col">Template</th>{bins.static.map((_, i) => <th scope="col" key={i}>{i + 1}</th>)}</tr>
          </thead>
          <tbody>
            <tr><th scope="row">Adaptive</th>{bins.adaptive.map((v, i) => <td key={i}>{pct(v)}</td>)}</tr>
            <tr><th scope="row">Static</th>{bins.static.map((v, i) => <td key={i}>{pct(v)}</td>)}</tr>
          </tbody>
        </table>
      </section>

      <section className="panel stack" aria-labelledby="drift-safety">
        <h2 id="drift-safety">Does adapting let someone else in?</h2>
        <p>
          After all the updates, other speakers' takes were checked against each final template
          ({data.impostor_trials} trials). Accepted: {pct(data.impostor_accept.adaptive)} with adaptation,
          {" "}{pct(data.impostor_accept.static)} without. Each update is limited to a cosine drift of {data.max_drift},
          and only takes that clear the threshold by {data.confident_margin} can move the template.
        </p>
        <table className="summary">
          <caption>Per speaker</caption>
          <thead>
            <tr><th scope="col">Speaker</th><th scope="col">Group</th><th scope="col">Takes</th>
              <th scope="col">Updates</th><th scope="col">Total drift</th></tr>
          </thead>
          <tbody>
            {speakers.map((s) => (
              <tr key={s.speaker}>
                <th scope="row">{s.speaker}</th><td>{s.group}</td><td>{s.points.length}</td>
                <td>{s.updates}</td><td>{s.total_drift.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="stack" aria-labelledby="drift-caveats">
        <h2 id="drift-caveats">What this does and does not show</h2>
        <ul>
          <li>TORGO recording sessions are days or weeks apart, not months. This shows the mechanism on real corpus audio; it is not evidence about how any condition progresses.</li>
          <li>Only speakers whose later takes come from a different session than enrollment are included. The template here is five different corpus words, not a sound the person chose.</li>
          <li>Small corpus, preliminary numbers. Generated {data.generated} by <code>make drift</code>.</li>
        </ul>
      </section>
    </div>
  );
}
