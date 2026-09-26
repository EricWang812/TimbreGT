import { useEffect, useRef, useState } from "react";
import {
  answerBasketClarification,
  extractAgenticBasket,
  prepareAgenticBasket,
  startBasketClarifications,
  transcribeAgenticShopping,
} from "../lib/api.js";
import { useCart } from "../lib/cart.jsx";
import { formatCents } from "../lib/money.js";
import { AGENTIC_MAX_SECONDS, startRecording } from "../lib/shoppingRecorder.js";
import { MicIcon, StopIcon } from "./Icons.jsx";
import {
  AGENTIC_VOICE_START_ID,
  AGENTIC_VOICE_TITLE_ID,
  requestStandardVoiceFallback,
} from "./jump.js";

const AGENTIC_TEXT_MAX = 1000;   // matches api/config.py AGENTIC_TEXT_MAX

const LABELS = {
  product: "Item", quantity: "Quantity", maxPrice: "Price limit", brand: "Brand",
  size: "Size", color: "Color", merchantPreference: "Merchant", useCase: "Use",
  importantRequirements: "Requirements", optionalPreferences: "Preferences", preferCheapest: "Choose",
};

function cartKey(lines) {
  return JSON.stringify([...lines].sort((a, b) => a.productId.localeCompare(b.productId)));
}

const toLines = (items) => items.map((line) => ({ productId: line.product_id, quantity: line.quantity }));

// Only what the shopper actually said: unstated fields are not listed, nor are
// ones the server set aside as never said (an inferred brand or pack size).
function spokenFields(intent, ignored = []) {
  const fields = Object.keys(LABELS).flatMap((field) => {
    if (ignored.includes(field)) return [];
    const entry = intent[field];
    if (field === "quantity" && entry?.mode === "fill_budget") return [[field, "As many as fit your limit"]];
    const value = Array.isArray(entry) ? (entry.length ? entry.join(", ") : null) : entry?.value;
    if (value == null) return [];
    if (field === "maxPrice") return [[field, `$${value}${entry.per === "each" ? " each" : ""}`]];
    return [[field, String(value)]];
  });
  return intent.preferCheapest ? [...fields, ["preferCheapest", "Cheapest match"]] : fields;
}

function productLabel(product) {
  return product.name.toLowerCase().includes(product.brand.toLowerCase()) ? product.name : `${product.brand} ${product.name}`;
}

export default function AgenticVoiceShopping({ onOpenCart }) {
  const cart = useCart();
  const latestLines = useRef(cart.lines);
  const recording = useRef(null);
  const timer = useRef(null);
  const controller = useRef(null);
  const run = useRef(0);
  const before = useRef(null);         // the cart when shopping started, for review and Undo
  const undoSnapshot = useRef(null);
  const correctionInput = useRef(null);
  const [phase, setPhase] = useState("idle");
  const [message, setMessage] = useState("");
  const [rawTranscript, setRawTranscript] = useState("");
  const [extraction, setExtraction] = useState(null);
  const [resolution, setResolution] = useState(null);
  const [result, setResult] = useState(null);
  const [skip, setSkip] = useState([]);
  const [correction, setCorrection] = useState("");
  const [typed, setTyped] = useState("");
  const [typedSource, setTypedSource] = useState(false);

  latestLines.current = cart.lines;
  const question = resolution?.pendingClarifications?.[0] ?? null;
  const busy = !["idle", "clarifying", "reviewing", "ready", "error"].includes(phase);
  const listening = phase === "listening";
  const request = extraction?.extractedRequest;
  const several = (request?.items?.length ?? 0) > 1;
  const active = !["idle", "ready", "error"].includes(phase);

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
    before.current = null;
    undoSnapshot.current = null;
    setPhase("idle"); setMessage(messageText); setRawTranscript(""); setExtraction(null);
    setResolution(null); setResult(null); setSkip([]); setCorrection("");
  }

  function apply(proposal) {
    if (cartKey(latestLines.current) !== cartKey(before.current)) {
      setPhase("error");
      setMessage("Your cart changed while Timbre was shopping, so nothing was added. Try again when you are ready.");
      return;
    }
    cart.replaceLines(proposal.items);
    undoSnapshot.current = { before: before.current, appliedKey: cartKey(toLines(proposal.items)) };
    setPhase("ready");
    setMessage(proposal.status === "needs_confirmation" ? "Added. Review your cart before checkout." : proposal.message);
  }

  async function prepare(state, skipped, signal, currentRun) {
    setPhase("shopping");
    before.current ??= latestLines.current;
    const proposal = await prepareAgenticBasket(state, before.current, skipped, signal);
    if (currentRun !== run.current) return;
    setResult(proposal);
    if (proposal.status === "no_matches") { setPhase("error"); setMessage(proposal.message); return; }
    if (proposal.status === "needs_confirmation") { setPhase("reviewing"); setMessage(""); return; }
    apply(proposal);
  }

  // The cart is the confirmation for named items: nothing is bought until
  // checkout, and one click takes the agent's change back out.
  function undo() {
    const snapshot = undoSnapshot.current;
    if (!snapshot) return;
    if (cartKey(latestLines.current) !== snapshot.appliedKey) {
      setMessage("Your cart has changed since then, so Timbre left it alone. You can edit it in the cart.");
      return;
    }
    cart.replaceLines(snapshot.before.map((line) => ({ product_id: line.productId, quantity: line.quantity })));
    undoSnapshot.current = null;
    setResult(null);
    setPhase("idle");
    setMessage("Removed. Your cart is back to how it was.");
  }

  async function continueResolution(state, signal, currentRun) {
    setResolution(state);
    if (state.pendingClarifications.length > 0) { setPhase("clarifying"); return; }
    await prepare(state, [], signal, currentRun);
  }

  async function guarded(currentRun, work, onError) {
    controller.current = new AbortController();
    try {
      await work(controller.current.signal);
    } catch (err) {
      if (currentRun === run.current && err.name !== "AbortError") onError(err);
    }
  }

  // Spoken and typed requests share everything after the words are known.
  async function interpret(text, signal, currentRun) {
    setRawTranscript(text);
    setPhase("interpreting");
    const extracted = await extractAgenticBasket(text, signal);
    if (currentRun !== run.current) return;
    setExtraction(extracted);
    const state = await startBasketClarifications(extracted, signal);
    if (currentRun !== run.current) return;
    await continueResolution(state, signal, currentRun);
  }

  async function processAudio(wav, currentRun) {
    await guarded(currentRun, async (signal) => {
      setPhase("transcribing");
      const transcription = await transcribeAgenticShopping(wav, signal);
      if (currentRun !== run.current) return;
      setTypedSource(false);
      await interpret(transcription.transcript, signal, currentRun);
    }, (err) => {
      if (err.status === 503 && requestStandardVoiceFallback(wav)) {
        setPhase("error");
        setMessage("Agentic shopping is unavailable, so Timbre continued with standard voice shopping.");
        return;
      }
      setPhase("error");
      setMessage(err.message || "Timbre could not process that request. Your cart was not changed.");
    });
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
      const take = await startRecording({ maxSeconds: AGENTIC_MAX_SECONDS });
      if (currentRun !== run.current) { await take.stop(); return; }
      recording.current = take;
      setPhase("listening");
      timer.current = setTimeout(stop, AGENTIC_MAX_SECONDS * 1000);
    } catch (err) {
      if (currentRun === run.current) { setPhase("error"); setMessage(err.message || "The microphone could not start."); }
    }
  }

  async function submitTyped(event) {
    event.preventDefault();
    const text = typed.trim();
    if (!text || busy || listening) return;
    reset();
    const currentRun = run.current;
    setTypedSource(true);
    setTyped("");
    await guarded(currentRun, (signal) => interpret(text, signal, currentRun), (err) => {
      setPhase("error");
      setMessage(err.status === 503
        ? "Agentic shopping is unavailable right now. Your cart was not changed."
        : err.message || "Timbre could not process that request. Your cart was not changed.");
    });
  }

  async function answer(action, value) {
    if (!question || busy) return;
    const currentRun = run.current;
    setPhase("interpreting"); setMessage("");
    await guarded(currentRun, async (signal) => {
      const state = await answerBasketClarification(
        resolution,
        { item: question.item, field: question.field, action, ...(action === "correct" ? { value } : {}) },
        signal,
      );
      if (currentRun !== run.current) return;
      setCorrection("");
      await continueResolution(state, signal, currentRun);
    }, (err) => { setPhase("clarifying"); setMessage(err.message); });
  }

  async function toggle(index) {
    if (busy) return;
    const next = skip.includes(index) ? skip.filter((i) => i !== index) : [...skip, index];
    setSkip(next);
    const currentRun = run.current;
    await guarded(currentRun, (signal) => prepare(resolution, next, signal, currentRun),
      (err) => { setPhase("reviewing"); setMessage(err.message); });
  }

  const progress = {
    starting: "Opening microphone…", listening: `Listening… up to ${AGENTIC_MAX_SECONDS} seconds.`,
    transcribing: "Transcribing…", interpreting: "Interpreting…", shopping: "Shopping…",
  }[phase];
  const kept = result?.lines?.filter((line) => line.product && line.quantity && !line.skipped) ?? [];

  return <section className="agentic-shopping stack" aria-labelledby={AGENTIC_VOICE_TITLE_ID}>
    <div className="section-head agentic-head">
      <div><p className="eyebrow">New agentic path</p><h2 id={AGENTIC_VOICE_TITLE_ID} tabIndex={-1}>Shop a full request by voice or text</h2></div>
      <p className="note">Say or type it the way you would to a person: “two cokes and as much yogurt as fits in ten dollars,” “what I need for tuna salad,” or “sunscreen, dog treats, and Bose earbuds.” It shops every shop on the boardwalk and asks only if it is unsure.</p>
    </div>
    <p>Timbre fills in your cart and shows you what it did. For a meal, it shows the list first. Nothing is bought until you check out.</p>
    <div className="voice-shopping-actions">
      <button id={AGENTIC_VOICE_START_ID} className={`btn btn-primary voice-mic${listening ? " is-recording" : ""}`} type="button" onClick={listening ? stop : record} disabled={busy && !listening} data-voice-active={active ? "" : undefined}>
        {listening ? <StopIcon size={22} /> : <MicIcon size={24} />}
        {listening ? "Stop recording" : "Speak a shopping request"}
      </button>
      {(busy || listening || phase === "clarifying" || phase === "reviewing") && <button className="btn btn-secondary" type="button" onClick={() => reset("Canceled. Your cart was not changed.")}>Cancel</button>}
      {listening && <span className="rec-indicator"><span className="rec-dot" aria-hidden="true" />Recording</span>}
    </div>
    <form className="voice-type" onSubmit={submitTyped}>
      <label htmlFor="agentic-typed">Or type the whole request</label>
      <div className="voice-type-row">
        <input id="agentic-typed" value={typed} onChange={(event) => setTyped(event.target.value)}
          maxLength={AGENTIC_TEXT_MAX} disabled={busy || listening} autoComplete="off"
          placeholder="two cokes and as much yogurt as fits in ten dollars" />
        <button className="btn btn-primary" type="submit" disabled={!typed.trim() || busy || listening}>Shop</button>
      </div>
    </form>
    <p className="voice-status" role="status" aria-live="polite">{progress || (phase === "ready" ? "" : message)}</p>

    {rawTranscript && <div className="agentic-block"><h3>{typedSource ? "You asked for" : "Timbre heard"}</h3><p className="agentic-transcript">“{rawTranscript}”</p></div>}
    {request && resolution && (request.items.length > 0 || request.meals.length > 0) && <div className="agentic-block"><h3>Timbre understood</h3>
      {request.items.map((item, i) => <div key={`item-${i}`} className="stack">
        {several && <p className="agentic-item-head">{item.product.value ?? `Item ${i + 1}`}</p>}
        <dl className="agentic-intent">{spokenFields(item, resolution.items?.[i]?.ignoredFields).map(([field, value]) => <div key={field}><dt>{LABELS[field]}</dt><dd>{value}</dd></div>)}</dl>
      </div>)}
      {request.meals.map((meal, i) => <p key={`meal-${i}`}><strong>Meal:</strong> {meal.goal}{meal.servings ? `, for ${meal.servings}` : ""}</p>)}
      {request.totalBudget?.value != null && <p><strong>Budget for everything:</strong> ${request.totalBudget.value}</p>}
    </div>}

    {question && phase === "clarifying" && <fieldset className="agentic-question">
      <legend>{several ? `About the ${question.itemLabel}: ` : ""}{question.question}</legend>
      {question.options.length > 0 ? <div className="voice-shopping-actions">
        {question.options.map((option) => <button key={option.action} className={option.action === "confirm" ? "btn btn-primary" : "btn btn-secondary"} type="button" onClick={() => answer(option.action)}>{option.label}</button>)}
      </div> : <form className="voice-type" onSubmit={(event) => { event.preventDefault(); if (correction.trim()) answer("correct", correction.trim()); }}>
        <label htmlFor="agentic-correction">Type your answer, or speak the whole request again</label>
        <div className="voice-type-row"><input ref={correctionInput} id="agentic-correction" value={correction} onChange={(event) => setCorrection(event.target.value)} maxLength={200} />
          <button className="btn btn-primary" type="submit" disabled={!correction.trim()}>Use this</button></div>
      </form>}
    </fieldset>}

    {phase === "reviewing" && result && <div className="agentic-ready" role="region" aria-labelledby="agentic-review-title">
      <h3 id="agentic-review-title">Check this list</h3>
      <p>{result.message}</p>
      <ul className="agentic-lines">
        {result.lines.filter((line) => line.product).map((line) => <li key={line.index} className={`agentic-line${line.skipped ? " is-skipped" : ""}`}>
          <div>
            <p className="agentic-line-name">{line.quantity} × {productLabel(line.product)}{line.skipped ? " (removed)" : ""}</p>
            <p className="note">{formatCents(line.lineCents)}{line.note ? ` · ${line.note}` : ""}</p>
          </div>
          <button className="btn btn-secondary" type="button" onClick={() => toggle(line.index)}
            aria-label={`${line.skipped ? "Put back" : "Remove"} ${productLabel(line.product)}`}>{line.skipped ? "Put back" : "Remove"}</button>
        </li>)}
      </ul>
      {result.notCarried.length > 0 && <p className="note">Not sold here: {result.notCarried.join(", ")}.</p>}
      {result.unverified.length > 0 && <p className="note">Could not check: {result.unverified.join(", ")}.</p>}
      {result.quote && <p className="note">Cart total with these: {formatCents(result.quote.total_cents)}, including tax and delivery.</p>}
      <div className="voice-shopping-actions">
        <button className="btn btn-primary" type="button" onClick={() => apply(result)} disabled={kept.length === 0}>Add {kept.length === 1 ? "it" : `these ${kept.length}`} to cart</button>
      </div>
    </div>}

    {phase === "ready" && result && <div className="agentic-ready" role="status">
      <h3>Added to your cart</h3>
      <p>{result.message}</p>
      {result.lines.filter((line) => line.note && line.source === "request").map((line) => <p key={line.index} className="note">{line.request}: {line.note}</p>)}
      {result.notCarried.length > 0 && <p className="note">Not sold here: {result.notCarried.join(", ")}.</p>}
      {result.assumptions.length > 0 && <p className="note">Assumed: {result.assumptions.join(" ")}</p>}
      {result.unverified.length > 0 && <p className="note">Could not check: {result.unverified.join(", ")}.</p>}
      {result.quote && <p className="note">Cart total {formatCents(result.quote.total_cents)}, including tax and delivery.</p>}
      <div className="voice-shopping-actions">
        <button className="btn btn-primary" type="button" onClick={onOpenCart}>Review cart</button>
        <a className="btn btn-secondary" href="#/checkout">Continue to checkout</a>
        <button className="btn btn-secondary" type="button" onClick={undo}>Undo</button>
      </div>
    </div>}
    {(phase === "error" || phase === "ready" || (phase === "idle" && message)) && <button className="btn btn-secondary agentic-restart" type="button" onClick={() => reset()}>Start another request</button>}
  </section>;
}
