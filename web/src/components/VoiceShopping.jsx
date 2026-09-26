import { useEffect, useRef, useState } from "react";
import { startRecording, MAX_SECONDS } from "../lib/shoppingRecorder.js";
import { shoppingText, shoppingVoice } from "../lib/api.js";
import { MAX_QUANTITY, useCart } from "../lib/cart.jsx";
import { useAnnounce } from "../lib/announce.jsx";
import { formatCents } from "../lib/money.js";

export default function VoiceShopping({ products }) {
  const cart = useCart();
  const announce = useAnnounce();
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

  useEffect(() => () => {
    generation.current += 1;
    clearTimeout(timer.current);
    controller.current?.abort();
    recording.current?.stop().catch((err) => console.warn("shopping recorder cleanup", err.name));
  }, []);
  useEffect(() => { if (suggestion) answer.current?.focus(); }, [suggestion]);

  async function interpret(send) {
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
        setSuggestion(product);
        setMessage(`${result.needs_repair ? "Did you mean" : "Add"} ${product.brand} ${product.name} for ${formatCents(product.price_cents)}?`);
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
      await interpret((signal) => shoppingVoice(wav, signal));
    } catch (err) {
      if (current === generation.current) { setMessage(err.message); setPhase("idle"); busy.current = false; }
    }
  }

  async function record() {
    if (busy.current) return;
    busy.current = true;
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
    interpret((signal) => shoppingText(text.trim(), signal));
  }

  function add() {
    if (!suggestion || cart.quantityOf(suggestion.id) >= MAX_QUANTITY) return;
    cart.add(suggestion.id);
    const message = `Added one ${suggestion.name} to your cart.`;
    setMessage(message); announce(message); setSuggestion(null);
  }

  return <section className="voice-shopping stack" aria-labelledby="voice-shopping-title">
    <h2 id="voice-shopping-title">Shop by voice</h2>
    <p>Name one item, then confirm it with a tap. Recording stops after {MAX_SECONDS} seconds. Shopping audio is used by the store to find an item; it is separate from your bank's voice approval.</p>
    <div className="voice-shopping-actions">
      <button className="btn btn-primary" type="button" disabled={phase === "starting" || phase === "thinking"}
        onClick={phase === "recording" ? stop : record}>{phase === "recording" ? "Stop recording" : phase === "starting" ? "Opening microphone…" : "Speak an item"}</button>
      {phase !== "idle" && <button className="btn btn-secondary" type="button" onClick={cancel}>Cancel</button>}
    </div>
    <form className="stack" onSubmit={submit}>
      <label htmlFor="shopping-text">Or type an item</label>
      <input id="shopping-text" value={text} onChange={(e) => setText(e.target.value)} maxLength={300} disabled={phase !== "idle"} />
      <button className="btn btn-secondary" type="submit" disabled={phase !== "idle" || !text.trim()}>Find this item</button>
    </form>
    <p role="status" aria-live="polite">{phase === "recording" ? "Recording. Say one item, then select Stop recording." : phase === "thinking" ? "Finding your item…" : message}</p>
    {suggestion && <div className="voice-shopping-actions">
      <button ref={answer} className="btn btn-primary" type="button" onClick={add} disabled={cart.quantityOf(suggestion.id) >= MAX_QUANTITY}>Yes, add one</button>
      <button className="btn btn-secondary" type="button" onClick={() => { setSuggestion(null); setMessage("Nothing added. Try another item or use the product buttons."); }}>No, try again</button>
      {cart.quantityOf(suggestion.id) >= MAX_QUANTITY && <p>You already have the maximum quantity of this item.</p>}
    </div>}
  </section>;
}
