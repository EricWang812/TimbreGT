// The issuer's verification widget: the bank's surface inside the checkout,
// like a 3-D Secure challenge (docs/DECISIONS.md ADR 2).
//
// Boundary rules, enforced by tests/test_guards.py:
//   - imports only React and files in src/issuer/
//   - tells the storefront nothing except that it closed (onClose takes no
//     arguments); the storefront then asks the merchant, which asks the
//     issuer, and learns only {verified, transaction_id}.
//
// Flow (docs/ALGORITHM.md §7.5, §7.6): choose the card -> the bank asks for
// two of the person's sounds in a random order -> both must match -> paid.
// Two failed attempts, no usable voiceprint, or a large amount lead to the
// passkey. Every path ends somewhere usable (non-negotiable §2.4).
import { useEffect, useRef, useState } from "react";
import { startAuthentication } from "@simplewebauthn/browser";
import {
  extendSession, getCardholders, getPasskeyOptions, getSession, identifyCardholder, submitPasskey, submitVoice,
} from "./issuerApi.js";
import { BankIcon, CheckIcon, ShieldIcon } from "./icons.jsx";
import { MAX_SECONDS, MicrophoneError, TooShortError, startRecording } from "./recorder.js";

const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const WARN_AT_SECONDS = 60;   // WCAG 2.2.1: warn before the time limit and offer more time
const WARN_BEFORE_STOP_SECONDS = 3;

const HEADINGS = {
  loading: "Checking with your bank",
  choose: "Confirm this payment",
  identifying: "One moment",
  voice: "Confirm it is you",
  checking: "Checking your voice",
  passkey: "Use your passkey",
  completing: "Approving payment",
  verified: "Payment approved",
  expired: "This request expired",
  error: "Something went wrong",
};
// Brief phases: focus stays where it is instead of jumping to the heading.
const TRANSIENT = new Set(["identifying", "checking", "completing"]);
const TIMED = new Set(["choose", "voice", "passkey"]);

function minutesText(seconds) {
  const m = Math.ceil(seconds / 60);
  return m === 1 ? "1 minute" : `${m} minutes`;
}

function Scores({ result }) {
  if (!result) return null;
  return (
    <div className="bank-card stack">
      <h3>Voice check</h3>
      <ul className="bank-scores">
        {result.takes.map((t) => (
          <li key={t.label}>
            <strong>&ldquo;{t.label}&rdquo;</strong>{" "}
            {t.passed ? <><CheckIcon size={18} /> matched</>
              : t.replay ? "rejected: this exact recording was used before"
              : t.threshold - t.score < 0.01 ? "just below your threshold" : "did not match"}
            <span className="bank-muted"> (score {t.score.toFixed(3)}, your threshold {t.threshold.toFixed(3)})</span>
          </li>
        ))}
      </ul>
      <p className="bank-muted">Checked in {(result.latency_ms / 1000).toFixed(1)} seconds. Only your bank sees these numbers.</p>
    </div>
  );
}

export default function ApprovalWidget({ sessionId, onClose }) {
  const dialogRef = useRef(null);
  const headingRef = useRef(null);
  const primaryRef = useRef(null);                     // the current main action, for focus after "more time"
  const [phase, setPhase] = useState("loading");
  const [message, setMessage] = useState("");          // errors: assertive
  const [status, setStatus] = useState("");            // progress: polite
  const [session, setSession] = useState(null);
  const [cardholders, setCardholders] = useState([]);
  const [selected, setSelected] = useState("");
  const [challenge, setChallenge] = useState([]);
  const [takes, setTakes] = useState([]);              // WAV blobs recorded so far, in challenge order
  const [recording, setRecording] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [passkeyMessage, setPasskeyMessage] = useState("");
  const [needsPasskeySetup, setNeedsPasskeySetup] = useState(false);
  const [deadline, setDeadline] = useState(null);      // ms timestamp when the bank request expires
  const [extensionsLeft, setExtensionsLeft] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const inFlight = useRef(false);                      // true while a request is pending: closing is blocked
  const recorder = useRef(null);                       // the live recording, if any (source of truth, not state)
  const starting = useRef(false);                      // true while the microphone is being opened
  const phaseRef = useRef("loading");                  // current phase for async continuations
  const errorRef = useRef(null);
  const timers = useRef({ limit: 0, warn: 0 });
  phaseRef.current = phase;

  // Stop any recording and its timers, discarding the take. Used on cancel,
  // expiry, and unmount, so the microphone is never left on.
  function stopMic() {
    clearTimeout(timers.current.limit);
    clearTimeout(timers.current.warn);
    const rec = recorder.current;
    recorder.current = null;
    setRecording(false);
    rec?.stop().catch((err) => console.info("recording discarded", err));
  }

  const secondsLeft = deadline === null ? null : Math.max(0, Math.round((deadline - now) / 1000));
  const warning = secondsLeft !== null && secondsLeft <= WARN_AT_SECONDS && TIMED.has(phase);

  useEffect(() => {
    if (deadline === null) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [deadline]);

  useEffect(() => {
    if (secondsLeft === 0 && TIMED.has(phase)) {
      stopMic();   // expiry mid-recording must not leave the microphone on
      setPhase("expired");
    }
  }, [secondsLeft, phase]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog.open) dialog.showModal();
    return () => {
      clearTimeout(timers.current.limit);
      clearTimeout(timers.current.warn);
      recorder.current?.stop().catch((err) => console.info("recording discarded on close", err));
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await getSession(sessionId);
        if (cancelled) return;
        setSession(s);
        setDeadline(Date.now() + s.seconds_remaining * 1000);
        setExtensionsLeft(s.extensions_left);
        if (s.status === "expired" || s.status === "verified") {
          setPhase(s.status);
          return;
        }
        const holders = await getCardholders(sessionId);
        if (cancelled) return;
        setCardholders(holders);
        setSelected(holders[0]?.id ?? "");
        setPhase("choose");
      } catch (err) {
        console.error("issuer widget failed to load", err);
        if (!cancelled) {
          setMessage("Your bank could not load this request. Return to the store and try again.");
          setPhase("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // On a phase change, focus the heading so it is announced; if the new phase
  // opens with an error, focus the error instead, so it is read once rather
  // than racing the heading.
  useEffect(() => {
    if (TRANSIENT.has(phase)) return;
    (errorRef.current ?? headingRef.current)?.focus();
  }, [phase]);

  // One wrapper for every bank request: blocks closing meanwhile, and maps an
  // expired session to the expired screen.
  async function call(fn) {
    inFlight.current = true;
    try {
      return await fn();
    } catch (err) {
      if (err.status === 410) {
        setPhase("expired");
        return null;
      }
      throw err;
    } finally {
      inFlight.current = false;
    }
  }

  async function moreTime() {
    try {
      const res = await extendSession(sessionId);
      setDeadline(Date.now() + res.seconds_remaining * 1000);
      setExtensionsLeft(res.extensions_left);
      setMessage("");
      // The "more time" button disappears with the warning; land on the next action.
      requestAnimationFrame(() => primaryRef.current?.focus());
    } catch (err) {
      console.error("issuer extend failed", err);
      if (err.status === 410) setPhase("expired");
      else setMessage("More time could not be added. Please finish now or return to the store.");
    }
  }

  async function chooseCard(event) {
    event.preventDefault();
    setMessage("");
    setPhase("identifying");
    try {
      const res = await call(() => identifyCardholder(sessionId, selected));
      if (!res) return;
      if (res.mode === "passkey") {
        setPasskeyMessage(res.message);
        setPhase("passkey");
        return;
      }
      setChallenge(res.challenge);
      setTakes([]);
      setStatus(res.step_up
        ? "This is a larger purchase: after your voice, your bank will also ask for your passkey."
        : "");
      setPhase("voice");
    } catch (err) {
      console.error("identify failed", err);
      setMessage(err.userMessage ?? "That card could not be used right now. Please try again.");
      setPhase("choose");
    }
  }

  async function toggleRecording() {
    // Refs, not state: a quick double-tap must never open a second recording
    // (state updates land only after the await, too late to guard).
    if (starting.current) return;
    if (recorder.current) return finishTake();
    setMessage("");
    starting.current = true;
    try {
      recorder.current = await startRecording();
    } catch (err) {
      console.error("microphone failed", err);
      setMessage(err instanceof MicrophoneError ? err.message : "Recording could not start. Please try again.");
      return;
    } finally {
      starting.current = false;
    }
    if (phaseRef.current !== "voice") {
      stopMic();   // the phase changed (expiry, cancel) while the mic was opening
      return;
    }
    setRecording(true);
    setStatus(`Recording "${challenge[takes.length]}". Tap Stop when you are done.`);
    timers.current.warn = setTimeout(() => setStatus(`${WARN_BEFORE_STOP_SECONDS} seconds left. Recording stops by itself.`),
      (MAX_SECONDS - WARN_BEFORE_STOP_SECONDS) * 1000);
    timers.current.limit = setTimeout(finishTake, MAX_SECONDS * 1000);
  }

  async function finishTake() {
    clearTimeout(timers.current.limit);
    clearTimeout(timers.current.warn);
    const rec = recorder.current;
    if (!rec) return;
    recorder.current = null;
    setRecording(false);
    let wav;
    try {
      ({ wav } = await rec.stop());
    } catch (err) {
      if (!(err instanceof TooShortError)) console.error("recording failed", err);
      setMessage(err instanceof TooShortError ? err.message : "That recording did not work. Please record it again.");
      return;
    }
    if (phaseRef.current !== "voice") return;   // expired or closed meanwhile: discard, send nothing
    const recorded = [...takes, wav];
    if (recorded.length < challenge.length) {
      setTakes(recorded);
      setStatus(`Got it. Now make your "${challenge[recorded.length]}" sound.`);
      return;
    }
    await checkVoice(recorded);
  }

  async function checkVoice(recorded) {
    setPhase("checking");
    setStatus("Checking your voice…");
    try {
      const res = await call(() => submitVoice(sessionId, recorded));
      if (!res) return;
      setLastResult(res);
      if (res.result === "verified") {
        setStatus("");
        setPhase("verified");
      } else if (res.result === "retry") {
        setChallenge(res.challenge);
        setTakes([]);
        setStatus(`That did not match. Let's try once more with a different pair. ${res.attempts_left} ${res.attempts_left === 1 ? "try" : "tries"} left.`);
        setPhase("voice");
      } else if (res.result === "passkey_required") {
        setPasskeyMessage(res.message);
        setPhase("passkey");
      } else {
        setTakes([]);
        setMessage("Your voice matched, but the card was declined. Record the sounds again to retry, or return to the store.");
        setPhase("voice");
      }
    } catch (err) {
      console.error("voice check failed", err);
      setTakes([]);
      setMessage(err.userMessage
        ? `${err.userMessage} Please record both sounds again.`
        : "Your voice could not be checked. Please record both sounds again.");
      setPhase("voice");
    }
  }

  async function passkey() {
    setMessage("");
    setNeedsPasskeySetup(false);
    setPhase("completing");
    try {
      const options = await call(() => getPasskeyOptions(sessionId));
      if (!options) return;
      // The device's own passkey prompt (Windows Hello, phone, security key).
      const credential = await startAuthentication({ optionsJSON: options });
      const res = await call(() => submitPasskey(sessionId, credential));
      if (!res) return;
      if (res.result === "verified") setPhase("verified");
      else {
        setMessage("The card was declined. Try again, or return to the store.");
        setPhase("passkey");
      }
    } catch (err) {
      if (err.userMessage === "no_passkey") {
        setNeedsPasskeySetup(true);
      } else if (err.name === "NotAllowedError" || err.name === "AbortError") {
        setMessage("The passkey request was cancelled or timed out. You can try again.");
      } else {
        console.error("passkey failed", err);
        setMessage(err.userMessage ?? "Your passkey could not be checked. Please try again.");
      }
      setPhase("passkey");
    }
  }

  // Closing mid-request would let the store ask for the result before the bank
  // has one, and a retry could charge twice. Block Escape and Cancel meanwhile.
  function blockCancelWhileBusy(event) {
    if (inFlight.current) event.preventDefault();
    else stopMic();   // Escape while recording: release the microphone now
  }
  const close = () => {
    if (inFlight.current) return;
    stopMic();
    dialogRef.current.close();  // fires the dialog's close event -> onClose
  };
  const done = phase === "verified" || phase === "expired" || phase === "error";
  const current = challenge[takes.length];

  return (
    <dialog ref={dialogRef} className="bank-dialog" aria-labelledby="bank-heading"
      onCancel={blockCancelWhileBusy} onClose={() => onClose()}>
      <div className="bank-header">
        <span className="bank-mark"><BankIcon /> Your bank</span>
        {!TRANSIENT.has(phase) && !done && (
          <button type="button" className="btn btn-bank-quiet" onClick={close}>Cancel</button>
        )}
      </div>

      <div className="bank-body">
        <p className="bank-muted"><ShieldIcon size={18} /> Card verification by your bank. The store never sees this step.</p>
        <h2 id="bank-heading" ref={headingRef} tabIndex={-1}>{HEADINGS[phase]}</h2>

        {session && (
          <div>
            <p className="bank-muted">Payment to {session.merchant_id}</p>
            <p className="bank-amount">{USD.format(session.amount_cents / 100)}</p>
          </div>
        )}

        <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">{status}</p>
        {status && <p className="bank-status" aria-hidden="true">{status}</p>}
        {message && <p className="bank-error" role="alert" ref={errorRef} tabIndex={-1}>{message}</p>}

        {TIMED.has(phase) && secondsLeft !== null && !warning && (
          <p className="bank-muted">This request stays open for about {minutesText(secondsLeft)}. You can ask for more time.</p>
        )}
        {warning && (
          <div className="bank-warning stack">
            {/* Static text in the alert so it is announced once, not every second. */}
            <p role="alert"><strong>Less than a minute left</strong> before this request expires.</p>
            <p className="bank-muted">{secondsLeft} seconds remaining</p>
            {extensionsLeft > 0 && (
              <button type="button" className="btn btn-bank btn-block" onClick={moreTime}>I need more time</button>
            )}
          </div>
        )}

        {(phase === "choose" || phase === "identifying") && (
          <form className="stack" onSubmit={chooseCard}>
            <fieldset className="bank-card-list" disabled={phase === "identifying"}>
              <legend>Pay with</legend>
              {cardholders.map((c) => (
                <label key={c.id} className="bank-card-option">
                  <input type="radio" name="cardholder" value={c.id}
                    checked={selected === c.id} onChange={() => setSelected(c.id)} />
                  <span>
                    <strong>{c.nickname} ending {c.last_four}</strong>
                    <br />
                    <span className="bank-muted">{c.display_name}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <button type="submit" ref={primaryRef} className="btn btn-bank btn-large btn-block"
              disabled={!selected || phase === "identifying"}>
              Continue
            </button>
          </form>
        )}

        {(phase === "voice" || phase === "checking") && (
          <div className="stack">
            <p>Your bank will ask for {challenge.length} of your sounds, one at a time.</p>
            <ol className="bank-steps">
              {challenge.map((label, i) => (
                <li key={`${label}-${i}`} aria-current={i === takes.length ? "step" : undefined}>
                  Make your <strong>&ldquo;{label}&rdquo;</strong> sound
                  {i < takes.length && <> <CheckIcon size={18} /> <span className="bank-muted">recorded</span></>}
                </li>
              ))}
            </ol>
            {phase === "voice" && current && (
              <button type="button" ref={primaryRef}
                className={`btn btn-bank btn-record${recording ? " is-recording" : ""}`}
                onClick={toggleRecording}>
                {recording ? `Stop recording "${current}"` : `Start recording "${current}"`}
              </button>
            )}
            {phase === "checking" && <p className="bank-muted" aria-busy="true">Checking your voice…</p>}
          </div>
        )}

        {(phase === "passkey" || phase === "completing") && (
          <div className="stack">
            <p>{passkeyMessage}</p>
            {needsPasskeySetup && (
              <div className="bank-warning stack">
                <p>There is no passkey for this card yet. Set one up in your bank app, then come back here:
                  this request stays open, and you can ask for more time.</p>
                <p>
                  <a className="bank-link" href={`#/bank/enroll/${encodeURIComponent(selected)}`}
                    target="_blank" rel="noopener noreferrer">
                    Open your bank app to set up a passkey (opens a new tab)
                  </a>
                </p>
              </div>
            )}
            <button type="button" ref={primaryRef} className="btn btn-bank btn-large btn-block"
              onClick={passkey} disabled={phase === "completing"}>
              {phase === "completing" ? "Waiting for your passkey…" : needsPasskeySetup ? "I have set it up. Try again" : "Use my passkey"}
            </button>
          </div>
        )}

        {phase !== "checking" && <Scores result={lastResult} />}

        {phase === "loading" && <p className="bank-muted">One moment…</p>}
        {phase === "verified" && (
          <p className="bank-ok"><CheckIcon size={20} /> Approved. You can return to the store.</p>
        )}
        {phase === "expired" && (
          <p className="bank-muted">For your security, this request timed out. Return to the store to start a new one.</p>
        )}

        {done && (
          <button type="button" className="btn btn-bank btn-large btn-block" onClick={close}>
            Return to the store
          </button>
        )}
      </div>
    </dialog>
  );
}
