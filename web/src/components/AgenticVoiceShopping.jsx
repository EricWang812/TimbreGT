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
  product: "Item", quantity: "Quantity", maxPrice: "Price limit", brand: "Brand",
  size: "Size", color: "Color", merchantPreference: "Merchant", useCase: "Use",
  importantRequirements: "Requirements", optionalPreferences: "Preferences", preferCheapest: "Choose",
};

function cartKey(lines) {
  return JSON.stringify([...lines].sort((a, b) => a.productId.localeCompare(b.productId)));
}

// Only what the shopper actually said: unstated fields are not listed.
function spokenFields(intent) {
  if (!intent) return [];
  const fields = Object.keys(LABELS).flatMap((field) => {
    const entry = intent[field];
    if (field === "quantity" && entry?.mode === "fill_budget") return [[field, "As many as fit your limit"]];
    const value = Array.isArray(entry) ? (entry.length ? entry.join(", ") : null) : entry?.value;
    if (value == null) return [];
    if (field === "maxPrice") return [[field, `$${value}${entry.per === "each" ? " each" : ""}`]];
    return [[field, String(value)]];
  });
  return intent.preferCheapest ? [...fields, ["preferCheapest", "Cheapest match"]] : fields;
}

function requestText(final) {
  const count = final.quantityMode === "fill_budget" ? "As many as fit" : `${final.quantity} ×`;
  const limit = final.maxPrice == null ? "no price limit"
    : `up to $${final.maxPrice}${final.pricePer === "each" ? " each" : ""}`;
  return `${count} ${final.brand ? `${final.brand} ` : ""}${final.product}, ${limit}${final.preferCheapest ? ", cheapest" : ""}.`;
}

export default function AgenticVoiceShopping({ onOpenCart }) {
  const cart = useCart();
  const latestLines = useRef(cart.lines);
  const recording = useRef(null);
  const timer = useRef(null);
  const controller = useRef(null);
  const run = useRef(0);
  const undoSnapshot = useRef(null);
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
  const understood = useMemo(() => spokenFields(intentResult?.extractedIntent), [intentResult]);
  const assumptions = finalized?.assumptions ?? resolution?.assumptions ?? [];

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
    undoSnapshot.current = null;
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
    const applied = result.items.map((line) => ({ productId: line.product_id, quantity: line.quantity }));
    undoSnapshot.current = { before, appliedKey: cartKey(applied) };
    setPhase("ready");
    setMessage(result.message || "Your cart is ready. Review it before checkout.");
  }

  // The cart is the confirmation: nothing is bought until checkout, and one
  // click takes the agent's change back out.
  function undo() {
    const snapshot = undoSnapshot.current;
    if (!snapshot) return;
    if (cartKey(latestLines.current) !== snapshot.appliedKey) {
      setMessage("Your cart has changed since then, so Timbre left it alone. You can edit it in the cart.");
      return;
    }
    cart.replaceLines(snapshot.before);
    undoSnapshot.current = null;
    setCommerce(null);
    setPhase("idle");
    setMessage("Removed. Your cart is back to how it was.");
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
  const final = finalized?.finalIntent;

  return <section className="agentic-shopping stack" aria-labelledby="agentic-shopping-title">
    <div className="section-head agentic-head">
      <div><p className="eyebrow">New agentic path</p><h2 id="agentic-shopping-title">Shop a full request by voice</h2></div>
      <p className="note">Say it the way you would to a person, for example “two bananas, under five dollars.” Timbre asks only if it is unsure.</p>
    </div>
    <p>Timbre fills in your cart and shows you what it did. Nothing is bought until you check out, and you can undo it in one step.</p>
    <div className="voice-shopping-actions">
      <button className={`btn btn-primary voice-mic${listening ? " is-recording" : ""}`} type="button" onClick={listening ? stop : record} disabled={busy && !listening}>
        {listening ? <StopIcon size={22} /> : <MicIcon size={24} />}
        {listening ? "Stop recording" : "Speak a shopping request"}
      </button>
      {(busy || listening || phase === "clarifying") && <button className="btn btn-secondary" type="button" onClick={() => reset("Canceled. Your cart was not changed.")}>Cancel</button>}
      {listening && <span className="rec-indicator"><span className="rec-dot" aria-hidden="true" />Recording</span>}
    </div>
    <p className="voice-status" role="status" aria-live="polite">{progress || (phase === "ready" ? "" : message)}</p>

    {rawTranscript && <div className="agentic-block"><h3>Timbre heard</h3><p className="agentic-transcript">“{rawTranscript}”</p></div>}
    {understood.length > 0 && <div className="agentic-block"><h3>Timbre understood</h3><dl className="agentic-intent">
      {understood.map(([field, value]) => <div key={field}><dt>{LABELS[field]}</dt><dd>{value}</dd></div>)}
    </dl></div>}

    {question && phase === "clarifying" && <fieldset className="agentic-question">
      <legend>{question.question}</legend>
      {question.options.length > 0 ? <div className="voice-shopping-actions">
        {question.options.map((option) => <button key={option.action} className={option.action === "confirm" ? "btn btn-primary" : "btn btn-secondary"} type="button" onClick={() => answer(option.action)}>{option.label}</button>)}
      </div> : <form className="voice-type" onSubmit={(event) => { event.preventDefault(); if (correction.trim()) answer("correct", correction.trim()); }}>
        <label htmlFor="agentic-correction">Type your answer, or speak the whole request again</label>
        <div className="voice-type-row"><input ref={correctionInput} id="agentic-correction" value={correction} onChange={(event) => setCorrection(event.target.value)} maxLength={200} />
          <button className="btn btn-primary" type="submit" disabled={!correction.trim()}>Use this</button></div>
      </form>}
    </fieldset>}

    {final && phase !== "ready" && <div className="agentic-block"><h3>Shopping for</h3><p>{requestText(final)}</p></div>}
    {phase === "ready" && commerce && <div className="agentic-ready" role="status">
      <h3>Added to your cart</h3>
      <p>{message}</p>
      {commerce.quote && <p className="note">Cart total {formatCents(commerce.quote.total_cents)}, including tax and delivery.</p>}
      {assumptions.length > 0 && <p className="note">Assumed: {assumptions.join(" ")}</p>}
      {commerce.unverifiedPreferences?.length > 0 && <p className="note">Could not check: {commerce.unverifiedPreferences.join(", ")}.</p>}
      <div className="voice-shopping-actions">
        <button className="btn btn-primary" type="button" onClick={onOpenCart}>Review cart</button>
        <a className="btn btn-secondary" href="#/checkout">Continue to checkout</a>
        <button className="btn btn-secondary" type="button" onClick={undo}>Undo</button>
      </div>
    </div>}
    {(phase === "error" || phase === "ready" || (phase === "idle" && message)) && <button className="btn btn-secondary agentic-restart" type="button" onClick={() => reset()}>Start another request</button>}
  </section>;
}
