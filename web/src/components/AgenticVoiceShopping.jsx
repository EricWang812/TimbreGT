import { useEffect, useMemo, useRef, useState } from "react";
import {
  answerAgenticClarification,
  extractAgenticIntent,
  finalizeAgenticShopping,
  prepareAgenticCart,
  startAgenticClarifications,
  transcribeAgenticShopping,
} from "../lib/api.js";
import { useCart } from "../lib/cart.jsx";
import { formatCents } from "../lib/money.js";
import { MAX_SECONDS, startRecording } from "../lib/shoppingRecorder.js";
import { MicIcon, StopIcon } from "./Icons.jsx";

const LABELS = {
  product: "Item", quantity: "Quantity", maxPrice: "Maximum price", brand: "Brand",
  size: "Size", color: "Color", merchantPreference: "Merchant", useCase: "Use",
  importantRequirements: "Requirements", optionalPreferences: "Preferences",
};

function cartKey(lines) {
  return JSON.stringify([...lines].sort((a, b) => a.productId.localeCompare(b.productId)));
}

function displayValue(field, intent) {
  const value = intent?.[field]?.value;
  if (value == null) return "Not specified";
  if (field === "maxPrice") return `${value} ${intent[field].currency ?? "USD"}`;
  return Array.isArray(value) ? value.join(", ") : String(value);
}

export default function AgenticVoiceShopping({ onOpenCart }) {
  const cart = useCart();
  const latestLines = useRef(cart.lines);
  const recording = useRef(null);
  const timer = useRef(null);
  const controller = useRef(null);
  const run = useRef(0);
  const correctionInput = useRef(null);
  const [phase, setPhase] = useState("idle");
  const [message, setMessage] = useState("");
  const [rawTranscript, setRawTranscript] = useState("");
  const [intentResult, setIntentResult] = useState(null);
  const [resolution, setResolution] = useState(null);
  const [finalized, setFinalized] = useState(null);
  const [commerce, setCommerce] = useState(null);
  const [correction, setCorrection] = useState("");

  latestLines.current = cart.lines;
  const question = resolution?.pendingClarifications?.[0] ?? null;
  const busy = !["idle", "clarifying", "ready", "error"].includes(phase);
  const listening = phase === "listening";
  const understood = useMemo(() => intentResult?.extractedIntent ?? null, [intentResult]);

  useEffect(() => () => {
    run.current += 1;
    clearTimeout(timer.current);
    controller.current?.abort();
    recording.current?.stop().catch(() => {});
  }, []);
  useEffect(() => { if (question?.options?.length === 0) correctionInput.current?.focus(); }, [question]);

  function reset(messageText = "") {
    run.current += 1;
    clearTimeout(timer.current);
    controller.current?.abort();
    recording.current?.stop().catch(() => {});
    recording.current = null;
    setPhase("idle"); setMessage(messageText); setRawTranscript(""); setIntentResult(null);
    setResolution(null); setFinalized(null); setCommerce(null); setCorrection("");
  }

  async function prepareCart(state, signal, currentRun) {
    setPhase("finalizing");
    const completed = await finalizeAgenticShopping(state, signal);
    if (currentRun !== run.current) return;
    setFinalized(completed);
    const before = latestLines.current;
    const beforeKey = cartKey(before);
    setPhase("shopping");
    const result = await prepareAgenticCart(completed, before, signal);
    if (currentRun !== run.current) return;
    setCommerce(result);
    if (result.status !== "cart_ready") {
      setPhase("error"); setMessage(result.message || "No matching products were found. Your cart was not changed."); return;
    }
    if (cartKey(latestLines.current) !== beforeKey) {
      setPhase("error"); setMessage("Your cart changed while Timbre was shopping, so the prepared cart was not applied. Try again when you are ready."); return;
    }
    cart.replaceLines(result.items);
    setPhase("ready");
    setMessage(result.message || "Your cart is ready. Review it before checkout.");
  }

  async function continueResolution(state, signal, currentRun) {
    setResolution(state);
    if (state.pendingClarifications.length > 0) { setPhase("clarifying"); return; }
    await prepareCart(state, signal, currentRun);
  }

  async function processAudio(wav, currentRun) {
    controller.current = new AbortController();
    const { signal } = controller.current;
    try {
      setPhase("transcribing");
      const transcription = await transcribeAgenticShopping(wav, signal);
      if (currentRun !== run.current) return;
      setRawTranscript(transcription.transcript);
      setPhase("interpreting");
      const intent = await extractAgenticIntent(transcription.transcript, signal);
      if (currentRun !== run.current) return;
      setIntentResult(intent);
      const state = await startAgenticClarifications(intent, signal);
      if (currentRun !== run.current) return;
      await continueResolution(state, signal, currentRun);
    } catch (err) {
      if (currentRun === run.current && err.name !== "AbortError") {
        setPhase("error"); setMessage(err.message || "Timbre could not process that request. Your cart was not changed.");
      }
    }
  }

  async function stop() {
    if (!recording.current) return;
    clearTimeout(timer.current);
    const take = recording.current;
    recording.current = null;
    const currentRun = run.current;
    setPhase("transcribing");
    try {
      const { wav } = await take.stop();
      if (currentRun === run.current) await processAudio(wav, currentRun);
    } catch (err) {
      if (currentRun === run.current) { setPhase("error"); setMessage(err.message || "Recording failed. Your cart was not changed."); }
    }
  }

  async function record() {
    if (busy || listening) return;
    reset();
    const currentRun = run.current;
    setPhase("starting");
    try {
      const take = await startRecording();
      if (currentRun !== run.current) { await take.stop(); return; }
      recording.current = take;
      setPhase("listening");
      timer.current = setTimeout(stop, MAX_SECONDS * 1000);
    } catch (err) {
      if (currentRun === run.current) { setPhase("error"); setMessage(err.message || "The microphone could not start."); }
    }
  }

  async function answer(action, value) {
    if (!question || busy) return;
    const currentRun = run.current;
    controller.current = new AbortController();
    setPhase("interpreting"); setMessage("");
    try {
      const state = await answerAgenticClarification(
        resolution,
        { field: question.field, action, ...(action === "correct" ? { value } : {}) },
        controller.current.signal,
      );
      if (currentRun !== run.current) return;
      setCorrection("");
      await continueResolution(state, controller.current.signal, currentRun);
    } catch (err) {
      if (currentRun === run.current && err.name !== "AbortError") { setPhase("clarifying"); setMessage(err.message); }
    }
  }

  const progress = {
    starting: "Opening microphone…", listening: "Listening…", transcribing: "Transcribing…",
    interpreting: "Interpreting…", finalizing: "Finalizing your request…", shopping: "Shopping…",
  }[phase];

  return <section className="agentic-shopping stack" aria-labelledby="agentic-shopping-title">
    <div className="section-head agentic-head">
      <div><p className="eyebrow">New agentic path</p><h2 id="agentic-shopping-title">Shop a full request by voice</h2></div>
      <p className="note">Timbre verifies the item, quantity, price, and any preferences you mention before preparing your cart.</p>
    </div>
    <p>Your existing voice shopping option above remains available. This assistant handles a complete request and asks about one field at a time.</p>
    <div className="voice-shopping-actions">
      <button className={`btn btn-primary voice-mic${listening ? " is-recording" : ""}`} type="button" onClick={listening ? stop : record} disabled={busy && !listening}>
        {listening ? <StopIcon size={22} /> : <MicIcon size={24} />}
        {listening ? "Stop recording" : "Speak a shopping request"}
      </button>
      {(busy || listening || phase === "clarifying") && <button className="btn btn-secondary" type="button" onClick={() => reset("Canceled. Your cart was not changed.")}>Cancel</button>}
      {listening && <span className="rec-indicator"><span className="rec-dot" aria-hidden="true" />Recording</span>}
    </div>
    <p className="voice-status" role="status" aria-live="polite">{progress || message}</p>

    {rawTranscript && <div className="agentic-block"><h3>Timbre heard</h3><p className="agentic-transcript">“{rawTranscript}”</p></div>}
    {understood && <div className="agentic-block"><h3>Timbre understood</h3><dl className="agentic-intent">
      {Object.keys(LABELS).map((field) => <div key={field}><dt>{LABELS[field]}</dt><dd>{displayValue(field, understood)}</dd></div>)}
    </dl></div>}

    {question && phase === "clarifying" && <fieldset className="agentic-question">
      <legend>{question.question}</legend>
      {question.heard && <p className="note">Heard: “{question.heard}”{question.proposed ? ` · Proposed: ${question.proposed}` : ""}</p>}
      {question.options.length > 0 ? <div className="voice-shopping-actions">
        {question.options.map((option) => <button key={option.action} className={option.action === "confirm" ? "btn btn-primary" : "btn btn-secondary"} type="button" onClick={() => answer(option.action)}>{option.label}</button>)}
      </div> : <form className="voice-type" onSubmit={(event) => { event.preventDefault(); if (correction.trim()) answer("correct", correction.trim()); }}>
        <label htmlFor="agentic-correction">Correct only this field</label>
        <div className="voice-type-row"><input ref={correctionInput} id="agentic-correction" value={correction} onChange={(event) => setCorrection(event.target.value)} maxLength={200} />
          <button className="btn btn-primary" type="submit" disabled={!correction.trim()}>Use correction</button></div>
      </form>}
    </fieldset>}

    {finalized && <div className="agentic-block"><h3>Shopping for</h3><p>{finalized.finalIntent.quantity} × {finalized.finalIntent.product}, up to {finalized.finalIntent.maxPrice} {finalized.finalIntent.currency ?? "USD"}.</p></div>}
    {phase === "ready" && commerce && <div className="agentic-ready" role="status">
      <h3>Cart ready</h3><p>{message}</p><p><strong>{commerce.selectedProduct?.brand} {commerce.selectedProduct?.name}</strong>{commerce.quote ? ` · ${formatCents(commerce.quote.total_cents)}` : ""}</p>
      {commerce.unverifiedPreferences?.length > 0 && <p className="note">Could not verify: {commerce.unverifiedPreferences.join(", ")}.</p>}
      <div className="voice-shopping-actions"><button className="btn btn-primary" type="button" onClick={onOpenCart}>Review cart</button><a className="btn btn-secondary" href="#/checkout">Continue to checkout</a></div>
    </div>}
    {(phase === "error" || phase === "ready") && <button className="btn btn-secondary agentic-restart" type="button" onClick={() => reset()}>Start another request</button>}
  </section>;
}
