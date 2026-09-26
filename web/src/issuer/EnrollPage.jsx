// The bank's voice setup screen. In a real deployment this lives inside the
// bank's own app (CLAUDE.md §1.1), so it is styled as the bank and imports
// only React and src/issuer/ (docs/DECISIONS.md ADR 2).
//
// Recording is tap to start, tap to stop. Never press-and-hold: holding a
// button down is hard for many people with motor impairments.
import { useEffect, useRef, useState } from "react";
import { startRegistration } from "@simplewebauthn/browser";
import {
  finalizeLabel, getEnrollment, getPasskeyCount, getRegistrationOptions, startLabelOver, submitRegistration,
  uploadSample,
} from "./issuerApi.js";
import { MAX_SECONDS, MIN_SECONDS, MicrophoneError, TooShortError, startRecording } from "./recorder.js";

const WARN_BEFORE_STOP_SECONDS = 3;   // one spoken heads-up before the automatic stop
import { BankIcon, CheckIcon } from "./icons.jsx";

// STUB: stands in for signing in to the bank. Mirrors scripts/seed_demo.py.
const DEMO_SIGN_IN = [
  { id: "maya", name: "Maya Torres" },
  { id: "jordan", name: "Jordan Lee" },
];

// Mirrors issuer/config.py STEP_UP_AMOUNT (cents); shown in the passkey explanation.
const STEP_UP_DOLLARS = 5000 / 100;

const STATUS_TEXT = {
  collecting: "In progress",
  enrolled: "Set up",
  low_confidence: "Set up, with passkey backup",
};

function BankShell({ children }) {
  return (
    <div className="bank-page">
      <header className="bank-page-header">
        <span className="bank-mark"><BankIcon /> Your bank</span>
        <a className="bank-link" href="#/">Back to Seaside Market</a>
      </header>
      <main id="main-content" className="bank-page-main" tabIndex={-1}>{children}</main>
    </div>
  );
}

function SignIn() {
  return (
    <BankShell>
      <div className="stack">
        <h1>Set up voice approval</h1>
        <p className="bank-muted">Demo sign-in: choose a cardholder. A real bank would already know who you are.</p>
        <ul className="bank-signin">
          {DEMO_SIGN_IN.map((u) => (
            <li key={u.id}>
              <a className="btn btn-bank btn-large btn-block" href={`#/bank/enroll/${u.id}`}>Continue as {u.name}</a>
            </li>
          ))}
        </ul>
      </div>
    </BankShell>
  );
}

// Interleaved enrollment (docs/DECISIONS.md ADR 4): once all sounds are named,
// the next take is always the sound with the fewest recordings (ties in list
// order). That records in rounds (a, b, c, a, b, c, ...), so each sound's
// takes are spread across the session rather than captured in one breath,
// and the template and its spread reflect how the person actually varies.
function nextTake(progress, planned) {
  const onServer = new Set(progress.labels.map((l) => l.label));
  const newNames = planned.filter((p) => !onServer.has(p));
  const collecting = [
    ...progress.labels.filter((l) => l.status === "collecting").map((l) => ({ label: l.label, samples: l.samples })),
    ...newNames.map((label) => ({ label, samples: 0 })),
  ];
  const namedCount = progress.labels.length + newNames.length;
  const allNamed = namedCount >= progress.labels_needed;
  const current = allNamed && collecting.length
    ? collecting.reduce((best, c) => (c.samples < best.samples ? c : best))
    : null;
  return { current, allNamed, namedCount, collecting };
}

function Enroll({ userId }) {
  const [progress, setProgress] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [planned, setPlanned] = useState([]);             // named, but no recording uploaded yet
  const [passkeys, setPasskeys] = useState(null);         // how many passkeys the cardholder has
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState("idle");             // idle | recording | saving
  const [elapsed, setElapsed] = useState(0);
  const [status, setStatus] = useState("");              // polite updates
  const [error, setError] = useState("");                 // assertive, actionable
  const recording = useRef(null);                          // the live recording (source of truth, not state)
  const starting = useRef(false);                          // true while the microphone is being opened
  const activeLabel = useRef("");                          // the label being recorded, fixed at start
  const timers = useRef({ tick: 0, limit: 0, warn: 0 });
  const meterRef = useRef(null);
  const headingRef = useRef(null);
  const labelInputRef = useRef(null);
  const recordButtonRef = useRef(null);

  async function refresh() {
    const p = await getEnrollment(userId);
    setProgress(p);
    return p;
  }

  useEffect(() => {
    getEnrollment(userId).then(setProgress, (err) => {
      console.error("enrollment load failed", err);
      setLoadError("Your bank could not load your voice setup. Reload the page to try again.");
    });
    getPasskeyCount(userId).then((r) => setPasskeys(r.count), (err) => {
      console.error("passkey count failed", err);
      setPasskeys(0);
    });
    return () => {
      clearInterval(timers.current.tick);
      clearTimeout(timers.current.limit);
      clearTimeout(timers.current.warn);
      // Release the microphone if the page is left mid-recording. The take is
      // discarded, so a rejection here (e.g. too short) is expected and logged.
      recording.current?.stop().catch((err) => console.info("recording discarded on leave", err));
    };
  }, [userId]);

  if (loadError) return <BankShell><p className="bank-error" role="alert">{loadError}</p></BankShell>;
  if (!progress) return <BankShell><p className="bank-muted">Loading…</p></BankShell>;

  const needed = progress.recordings_per_label;
  const finished = progress.labels.filter((l) => l.status !== "collecting");
  const done = finished.length >= progress.labels_needed;
  const { current, allNamed, namedCount } = nextTake(progress, planned);

  async function toggleRecording() {
    // Refs, not state: a quick double-tap must never open a second recording.
    if (starting.current || phase === "saving") return;   // aria-disabled keeps keyboard focus here
    if (recording.current) return finish();
    setError("");
    starting.current = true;
    try {
      recording.current = await startRecording({
        onLevel: (level) => {
          if (meterRef.current) meterRef.current.style.transform = `scaleX(${Math.min(1, level * 6)})`;
        },
      });
    } catch (err) {
      console.error("microphone failed", err);
      setError(err instanceof MicrophoneError ? err.message : "Recording could not start. Please try again.");
      return;
    } finally {
      starting.current = false;
    }
    const started = Date.now();
    activeLabel.current = current.label;
    setElapsed(0);
    setPhase("recording");
    setStatus("Recording. Tap Stop when you are done.");
    timers.current.tick = setInterval(() => setElapsed((Date.now() - started) / 1000), 100);
    timers.current.warn = setTimeout(
      () => setStatus(`${WARN_BEFORE_STOP_SECONDS} seconds left. Recording stops by itself.`),
      (MAX_SECONDS - WARN_BEFORE_STOP_SECONDS) * 1000,
    );
    timers.current.limit = setTimeout(finish, MAX_SECONDS * 1000);
  }

  async function finish() {
    clearInterval(timers.current.tick);
    clearTimeout(timers.current.limit);
    clearTimeout(timers.current.warn);
    const rec = recording.current;
    if (!rec) return;
    recording.current = null;
    const label = activeLabel.current;       // not the render closure: fixed when recording began
    setPhase("saving");
    setStatus("Saving…");
    try {
      const { wav } = await rec.stop();
      const saved = await uploadSample(userId, label, wav);
      const stillPlanned = planned.filter((p) => p !== label);   // this label now exists on the server
      setPlanned(stillPlanned);
      let prefix = `Got it: "${label}", ${saved.samples} of ${saved.needed}.`;
      let rerecord = false;
      if (saved.samples >= saved.needed) {
        const result = await finalizeLabel(userId, label);
        rerecord = result.status === "rerecord";
        prefix = rerecord ? result.message
          : `"${label}" is set up. ${result.message === "Saved." ? "" : result.message}`.trim();
      }
      const p = await refresh();
      const nowDone = p.labels.filter((l) => l.status !== "collecting").length >= p.labels_needed;
      const next = nextTake(p, stillPlanned).current;
      setStatus(next && !nowDone ? `${prefix} Next: your "${next.label}" sound.` : prefix);
      // Focus what comes next: the heading when finished, else the record button.
      requestAnimationFrame(() => (nowDone ? headingRef : rerecord || next ? recordButtonRef : labelInputRef)
        .current?.focus());
    } catch (err) {
      if (err instanceof TooShortError) {
        setError(err.message);
      } else {
        console.error("saving the recording failed", err);
        setError(err.userMessage ?? "That recording could not be saved. Please record it again.");
      }
      setStatus("");
    } finally {
      setPhase("idle");
      if (meterRef.current) meterRef.current.style.transform = "scaleX(0)";
    }
  }

  async function startOver(label) {
    setError("");
    if (planned.includes(label)) {
      // Named but never recorded: nothing to remove at the bank.
      setPlanned(planned.filter((p) => p !== label));
      setStatus(`"${label}" removed. You can name a new sound.`);
      requestAnimationFrame(() => labelInputRef.current?.focus());
      return;
    }
    try {
      setProgress(await startLabelOver(userId, label));
      setStatus(`"${label}" removed. You can name a new sound.`);
    } catch (err) {
      console.error("start over failed", err);
      setError("That sound could not be removed. Please try again.");
    }
  }

  async function addPasskey() {
    setError("");
    setPasskeyBusy(true);
    try {
      const options = await getRegistrationOptions(userId);
      // The device's own prompt (Windows Hello, phone, security key).
      const credential = await startRegistration({ optionsJSON: options });
      const res = await submitRegistration(userId, credential);
      setPasskeys(res.count);
      setStatus("Passkey set up. Your bank can use it as a backup to your voice.");
    } catch (err) {
      if (err.name === "InvalidStateError") {
        setError("This device already has a passkey for this card.");
      } else if (err.name === "NotAllowedError" || err.name === "AbortError") {
        setError("Passkey setup was cancelled or timed out. You can try again.");
      } else {
        console.error("passkey registration failed", err);
        setError(err.userMessage ?? "The passkey could not be set up. Please try again.");
      }
    } finally {
      setPasskeyBusy(false);
    }
  }

  function nameSound(event) {
    event.preventDefault();
    const label = draft.trim();
    if (!label) {
      setError("Give the sound a name first, for example: hum.");
      return;
    }
    if (progress.labels.some((l) => l.label === label) || planned.includes(label)) {
      setError(`You already have a sound called "${label}". Choose another name.`);
      return;
    }
    setError("");
    const nowPlanned = [...planned, label];
    setPlanned(nowPlanned);
    setDraft("");
    const next = nextTake(progress, nowPlanned);
    if (next.allNamed) {
      setStatus(`All ${progress.labels_needed} sounds named. Round 1: make your "${next.current.label}" sound.`);
      requestAnimationFrame(() => recordButtonRef.current?.focus());
    } else {
      setStatus(`"${label}" added. Name sound ${next.namedCount + 1}.`);
      requestAnimationFrame(() => labelInputRef.current?.focus());
    }
  }

  return (
    <BankShell>
      <div className="stack">
        <h1 ref={headingRef} tabIndex={-1}>{done ? "Your voice is set up" : "Set up voice approval"}</h1>
        <p className="bank-muted">
          Signed in as {progress.display_name}. Choose {progress.labels_needed} sounds you can make the same way
          each time, then record each one {needed} times. Your bank asks for them in turn, so each sound is
          recorded at a few different moments; that helps it recognize you on another day. Words or short
          phrases you say easily work best. A headset microphone helps.
        </p>

        <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">{status}</p>
        {status && <p className="bank-status" aria-hidden="true">{status}</p>}
        {error && <p className="bank-error" role="alert">{error}</p>}

        <section aria-labelledby="sounds-heading" className="bank-card stack">
          <h2 id="sounds-heading">Your sounds ({finished.length} of {progress.labels_needed} set up)</h2>
          {namedCount === 0 && <p className="bank-muted">None yet.</p>}
          <ul className="bank-sound-list">
            {[...progress.labels, ...planned
              .filter((p) => !progress.labels.some((l) => l.label === p))
              .map((label) => ({ label, status: "collecting", samples: 0 }))].map((l) => (
              <li key={l.label}>
                <span>
                  <strong>{l.label}</strong>{" "}
                  <span className="bank-muted">
                    {l.status === "collecting" ? `${l.samples} of ${needed} recordings` : STATUS_TEXT[l.status]}
                  </span>{" "}
                  {l.status !== "collecting" && <CheckIcon size={18} />}
                </span>
                <button type="button" className="btn btn-bank-quiet" onClick={() => startOver(l.label)}
                  disabled={phase !== "idle"} aria-label={`Start over: ${l.label}`}>
                  Start over
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="bank-card stack" aria-labelledby="passkey-heading">
          <h2 id="passkey-heading">Passkey backup</h2>
          <p>
            If your voice is not recognized, and for purchases of ${STEP_UP_DOLLARS} or more, your bank also asks
            for a passkey: Windows Hello, your phone, or a security key.
          </p>
          <p className="bank-muted">
            {passkeys === null ? "Checking…" : passkeys > 0
              ? `Set up (${passkeys} ${passkeys === 1 ? "passkey" : "passkeys"}).` : "Not set up yet."}
          </p>
          <button type="button" className="btn btn-bank btn-block" onClick={addPasskey}
            disabled={passkeyBusy || phase !== "idle"}>
            {passkeyBusy ? "Waiting for your device…" : passkeys > 0 ? "Add another passkey" : "Set up a passkey"}
          </button>
        </section>

        {done && (
          <section className="bank-card stack" aria-labelledby="done-heading">
            <h2 id="done-heading">All set</h2>
            <p>Your bank can now recognize your voice when you approve a payment.</p>
            <a className="btn btn-bank btn-large btn-block" href="#/">Back to Seaside Market</a>
          </section>
        )}

        {!done && current && (
          <section className="bank-card stack" aria-labelledby="record-heading">
            <h2 id="record-heading">
              Round {Math.min(current.samples + 1, needed)} of {needed}: your &ldquo;{current.label}&rdquo; sound
            </h2>
            <p>
              Make the sound, then tap Stop. At least {MIN_SECONDS} seconds, at most {MAX_SECONDS}.
              Take a breath between recordings; they do not need to be identical.
            </p>
            <div className="bank-meter" aria-hidden="true"><div ref={meterRef} className="bank-meter-fill" /></div>
            {/* Elapsed time is visual only: changing the button's own name every
                100 ms would make screen readers re-announce it constantly. */}
            {phase === "recording" && <p className="bank-timer" aria-hidden="true">{elapsed.toFixed(1)} s</p>}
            <button type="button" ref={recordButtonRef}
              className={`btn btn-bank btn-record${phase === "recording" ? " is-recording" : ""}`}
              onClick={toggleRecording} aria-disabled={phase === "saving"}>
              {phase === "saving" ? "Saving…" : phase === "recording" ? "Stop recording" : "Start recording"}
            </button>
          </section>
        )}

        {!done && !allNamed && (
          <form className="bank-card stack" onSubmit={nameSound} aria-labelledby="name-heading">
            <h2 id="name-heading">Name sound {namedCount + 1} of {progress.labels_needed}</h2>
            <label htmlFor="sound-name">Name this sound</label>
            <p id="sound-name-help" className="bank-muted">
              For example a word or short phrase you say easily, like a pet&rsquo;s name or a place.
              Hums and single vowels carry less of your voice.
            </p>
            <input id="sound-name" ref={labelInputRef} className="bank-input" value={draft}
              onChange={(e) => setDraft(e.target.value)} maxLength={32} aria-describedby="sound-name-help"
              autoComplete="off" />
            <button type="submit" className="btn btn-bank btn-large btn-block">Add this sound</button>
          </form>
        )}
      </div>
    </BankShell>
  );
}

export default function EnrollPage({ userId }) {
  return userId ? <Enroll key={userId} userId={userId} /> : <SignIn />;
}
