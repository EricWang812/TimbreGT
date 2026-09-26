// Spoken readback for the store's voice shopping (docs/ALGORITHM.md §10.3).
// The store's own copy: the bank widget has a separate one in src/issuer/
// because the two sides must not share code (tests/test_guards.py).

export function canSpeak() {
  return typeof window !== "undefined" && "speechSynthesis" in window
    && typeof window.SpeechSynthesisUtterance === "function";
}

export function speak(text) {
  if (!canSpeak()) return false;
  window.speechSynthesis.cancel();                 // never queue behind an older readback
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
  return true;
}

// Called before the microphone opens, so the readback is not recorded.
export function stopSpeaking() {
  if (canSpeak()) window.speechSynthesis.cancel();
}
