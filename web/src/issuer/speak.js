// Spoken readback on the bank's own surface (docs/ALGORITHM.md §10.3).
// Fixed wording with the numbers inserted as data: nothing here composes free
// text or computes a total, so the spoken amount is always the one on screen.
// Kept inside src/issuer/ because the widget may import only its own folder.

export function canSpeak() {
  return typeof window !== "undefined" && "speechSynthesis" in window
    && typeof window.SpeechSynthesisUtterance === "function";
}

export function speak(text) {
  if (!canSpeak()) return false;
  window.speechSynthesis.cancel();                 // never queue behind an older readback
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 0.9;                            // a little slower than default, for clarity
  window.speechSynthesis.speak(utterance);
  return true;
}

// Called before the microphone opens: the readback must not end up in a take.
export function stopSpeaking() {
  if (canSpeak()) window.speechSynthesis.cancel();
}

// "Pay $12.34 to seaside market with your Visa ending 4 2 4 2."
// Digits are spaced so they are read one by one, not as "four thousand...".
export function paymentSentence({ amountText, merchant, card }) {
  const to = String(merchant).replace(/[-_]+/g, " ");
  const withCard = card ? ` with your ${card.nickname} ending ${card.last_four.split("").join(" ")}` : "";
  return `Pay ${amountText} to ${to}${withCard}.`;
}
