import { useEffect, useRef, useState } from "react";
import { startRecording, MAX_SECONDS } from "../lib/shoppingRecorder.js";
import { shoppingText, shoppingVoice } from "../lib/api.js";
import { MAX_QUANTITY, useCart } from "../lib/cart.jsx";
import { formatCents } from "../lib/money.js";
import { canSpeak, speak, stopSpeaking } from "../lib/speak.js";
import { MicIcon, StopIcon } from "./Icons.jsx";
import { STANDARD_VOICE_FALLBACK_EVENT, VOICE_START_ID, VOICE_TITLE_ID } from "./jump.js";

// Remembered per browser. A screen reader already speaks the status line, so
// people using one may want the app's own voice off (the two would overlap).
const READ_ALOUD_KEY = "seaside-read-aloud";
function loadReadAloud() {
  try {
    return localStorage.getItem(READ_ALOUD_KEY) !== "off";
  } catch (err) {
    console.warn("read-aloud preference unavailable", err);
    return true;
  }
}

export default function VoiceShopping({ products, marketId }) {
  const cart = useCart();
  const [readAloud, setReadAloud] = useState(loadReadAloud);
  const [phase, setPhase] = useState("idle");
  const [text, setText] = useState("");
  const [message, setMessage] = useState("");
  const [suggestion, setSuggestion] = useState(null);
  const recording = useRef(null);
  const timer = useRef(null);
  const busy = useRef(false);
  const generation = useRef(0);
  const controller = useRef(null);
  const answer = useRef(null);
  const fallbackRequest = useRef(null);

  useEffect(() => () => {
    generation.current += 1;
    clearTimeout(timer.current);
    controller.current?.abort();
    recording.current?.stop().catch((err) => console.warn("shopping recorder cleanup", err.name));
    stopSpeaking();
  }, []);
  useEffect(() => { if (suggestion) answer.current?.focus(); }, [suggestion]);

  // The agentic panel dispatches its already-recorded WAV here only when an
  // agentic service is unavailable. Reuse the existing Whisper path and its
  // confirmation UI, so the shopper never has to say the request again.
  fallbackRequest.current = (event) => {
    if (busy.current || !(event.detail?.wav instanceof Blob)) return;
    event.preventDefault();
    busy.current = true;
    stopSpeaking();
    setMessage("Agentic shopping is unavailable. Using standard voice shopping…");
    interpret((signal) => shoppingVoice(event.detail.wav, signal, marketId), true);
  };
  useEffect(() => {
    const handleFallback = (event) => fallbackRequest.current?.(event);
    window.addEventListener(STANDARD_VOICE_FALLBACK_EVENT, handleFallback);
    return () => window.removeEventListener(STANDARD_VOICE_FALLBACK_EVENT, handleFallback);
  }, []);

  // spoken: the request came by voice, so the answer is read aloud too.
  async function interpret(send, spoken = false) {
    const current = generation.current;
    setPhase("thinking");
    setSuggestion(null);
    controller.current = new AbortController();
    try {
      const result = await send(controller.current.signal);
      if (current !== generation.current) return;
      const product = products.find((p) => p.id === result.product_id);
      if (!product) setMessage("I could not find one item. Try its name, type below, or use the product buttons.");
      else {
        const full = cart.quantityOf(product.id) >= MAX_QUANTITY;
        const question = `${result.needs_repair ? "Did you mean" : "Add"} ${product.brand} ${product.name} for ${formatCents(product.price_cents)}?`
          + (full ? ` You already have the maximum of ${MAX_QUANTITY}.` : "");
        setSuggestion(product);
        setMessage(question);
        if (spoken && readAloud) speak(question);
      }
    } catch (err) {
      if (current === generation.current && err.name !== "AbortError") {
        setMessage(err.message || "Please type an item or use the product buttons.");
      }
    } finally {
      if (current === generation.current) { busy.current = false; setPhase("idle"); }
    }
  }

  async function stop() {
    if (!recording.current) return;
    clearTimeout(timer.current);
    const take = recording.current;
    recording.current = null;
    setPhase("thinking");
    const current = generation.current;
    try {
      const { wav } = await take.stop();
      if (current !== generation.current) return;
      await interpret((signal) => shoppingVoice(wav, signal, marketId), true);
    } catch (err) {
      if (current === generation.current) { setMessage(err.message); setPhase("idle"); busy.current = false; }
    }
  }

  async function record() {
    if (busy.current) return;
    busy.current = true;
    stopSpeaking();   // never record the readback
    setMessage(""); setSuggestion(null); setPhase("starting");
    const current = generation.current;
    try {
      const take = await startRecording();
      if (current !== generation.current) { await take.stop(); return; }
      recording.current = take;
      setPhase("recording");
      timer.current = setTimeout(stop, MAX_SECONDS * 1000);
    } catch (err) {
      if (current === generation.current) { setMessage(err.message); setPhase("idle"); busy.current = false; }
    }
  }

  function cancel() {
    generation.current += 1;
    clearTimeout(timer.current);
    controller.current?.abort();
    recording.current?.stop().catch((err) => console.warn("shopping recorder canceled", err.name));
    recording.current = null;
    busy.current = false; setPhase("idle"); setSuggestion(null); setMessage("Canceled. You can use the product buttons.");
  }

  function submit(event) {
    event.preventDefault();
    if (busy.current || !text.trim()) return;
    busy.current = true; setMessage("");
    interpret((signal) => shoppingText(text.trim(), signal, marketId));
  }

  function add() {
    if (!suggestion) return;
    if (cart.quantityOf(suggestion.id) >= MAX_QUANTITY) {
      // aria-disabled keeps focus here, so say why nothing was added.
      setMessage(`You already have the maximum of ${MAX_QUANTITY} ${suggestion.name}. Nothing was added.`);
      return;
    }
    cart.add(suggestion.id);
    // One announcement: the status line below is this panel's live region.
    setMessage(`Added one ${suggestion.name} to your cart.`);
    setSuggestion(null);
    focusSpeak();
  }

  function toggleReadAloud(event) {
    const on = event.target.checked;
    setReadAloud(on);
    if (!on) stopSpeaking();
    try {
      localStorage.setItem(READ_ALOUD_KEY, on ? "on" : "off");
    } catch (err) {
      console.warn("could not save the read-aloud preference", err);
    }
  }

  // The answer buttons unmount after a choice; land keyboard focus on the next
  // natural action instead of letting it fall to the page body.
  function focusSpeak() {
    requestAnimationFrame(() => document.getElementById(VOICE_START_ID)?.focus());
  }

  const listening = phase === "recording";
  const atMax = suggestion ? cart.quantityOf(suggestion.id) >= MAX_QUANTITY : false;

  return <section className="voice-shopping" aria-labelledby={VOICE_TITLE_ID}>
    <div className="voice-intro">
      <h2 id={VOICE_TITLE_ID} tabIndex={-1}>Shop by voice</h2>
      <p className="voice-explain">Name one item, then confirm it with a tap. Recording stops after {MAX_SECONDS} seconds. Shopping audio is used by the store to find an item; it is separate from your bank's voice approval.</p>
    </div>
    <div className="voice-shopping-actions">
      <button id={VOICE_START_ID} className={`btn btn-primary voice-mic${listening ? " is-recording" : ""}`} type="button"
        disabled={phase === "starting" || phase === "thinking"}
        data-voice-active={phase !== "idle" ? "" : undefined}
        onClick={listening ? stop : record}>
        {listening ? <StopIcon size={22} /> : <MicIcon size={24} />}
        {listening ? "Stop recording" : phase === "starting" ? "Opening microphone…" : "Speak an item"}
      </button>
      {phase !== "idle" && <button className="btn btn-secondary" type="button" onClick={cancel}>Cancel</button>}
      {/* A13: the word "Recording" carries the state; the dot only reinforces it. */}
      {listening && <span className="rec-indicator"><span className="rec-dot" aria-hidden="true" />Recording</span>}
    </div>
    <form className="voice-type" onSubmit={submit}>
      <label htmlFor="shopping-text">Or type an item</label>
      <div className="voice-type-row">
        <input id="shopping-text" value={text} onChange={(e) => setText(e.target.value)} maxLength={300} disabled={phase !== "idle"} />
        <button className="btn btn-secondary" type="submit" disabled={phase !== "idle" || !text.trim()}>Find this item</button>
      </div>
    </form>
    <p className="voice-status" role="status" aria-live="polite">{listening ? "Recording. Say one item, then select Stop recording." : phase === "thinking" ? "Finding your item…" : message}</p>
    {/* A12: the suggestion fades and rises in (styles.css); focus moves to "Yes, add one". */}
    {suggestion && <div className="voice-suggestion">
      <div className="voice-suggestion-item">
        <img className="voice-suggestion-photo" src={suggestion.image_url} alt="" width="64" height="64" decoding="async" />
        <div>
          <p className="product-brand">{suggestion.brand}</p>
          <p className="voice-suggestion-name">{suggestion.name}</p>
          <p className="price">{formatCents(suggestion.price_cents)}</p>
        </div>
      </div>
      <div className="voice-shopping-actions">
        <button ref={answer} className="btn btn-primary" type="button" onClick={add} aria-disabled={atMax || undefined}>Yes, add one</button>
        <button className="btn btn-secondary" type="button" onClick={() => { stopSpeaking(); setSuggestion(null); setMessage("Nothing added. Try another item or use the product buttons."); focusSpeak(); }}>No, try again</button>
        {canSpeak() && <button className="btn btn-secondary" type="button" onClick={() => speak(message)}>Say it again</button>}
      </div>
      {atMax && <p className="note">You already have the maximum quantity of this item.</p>}
    </div>}
    {canSpeak() && <label className="voice-readaloud">
      <input type="checkbox" checked={readAloud} onChange={toggleReadAloud} />
      Read suggestions aloud after I speak
    </label>}
  </section>;
}
