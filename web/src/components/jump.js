// In-page jumps for the store (aisle chips, the header's "Shop by voice" link).
// A plain href="#pantry" would be read as a route by the hash router, so every
// jump is handled in JavaScript: scroll, then move focus to the target.
import { navigate } from "../lib/router.js";

// Stable ids so other store components (the header link, the cart drawer's
// empty state) can reach the voice panel without importing it.
export const VOICE_START_ID = "voice-shopping-start";
export const VOICE_TITLE_ID = "voice-shopping-title";
export const AGENTIC_VOICE_START_ID = "agentic-voice-shopping-start";
export const AGENTIC_VOICE_TITLE_ID = "agentic-shopping-title";
export const STANDARD_VOICE_FALLBACK_EVENT = "timbre:standard-voice-fallback";

export function prefersMotion() {
  return window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
}

// Smooth scroll only when the person has not asked for reduced motion (A15).
// Focus uses preventScroll so it does not cancel the smooth scroll.
export function scrollAndFocus(scrollTarget, focusTarget = scrollTarget) {
  scrollTarget.scrollIntoView({ behavior: prefersMotion() ? "smooth" : "auto", block: "start" });
  focusTarget.focus({ preventScroll: true });
}

// Scrolls to the voice panel and focuses "Speak an item" (or the panel heading
// while that button is busy). From another page, goes to the shop first and
// waits up to about one second for the panel to mount.
export function focusVoiceShopping() {
  function attempt(framesLeft) {
    const button = document.getElementById(VOICE_START_ID);
    const title = document.getElementById(VOICE_TITLE_ID);
    if (button && title) {
      const section = title.closest("section") ?? title;
      scrollAndFocus(section, button.disabled ? title : button);
      return;
    }
    if (framesLeft > 0) requestAnimationFrame(() => attempt(framesLeft - 1));
  }
  if (!document.getElementById(VOICE_START_ID)) navigate("/");
  attempt(60);
}

// The header starts the full-request agent when it is on the page. The
// original Whisper recorder remains the fallback when that additive panel is
// unavailable. A disabled recorder is already doing work, so focus its title
// instead of starting the other recorder at the same time.
export function startHeaderVoiceShopping() {
  function start(buttonId, titleId) {
    const button = document.getElementById(buttonId);
    const title = document.getElementById(titleId);
    if (!button || !title) return false;
    const section = title.closest("section") ?? title;
    const active = button.hasAttribute("data-voice-active");
    scrollAndFocus(section, button.disabled || active ? title : button);
    if (!button.disabled && !active) button.click();
    return true;
  }

  function attempt(framesLeft) {
    if (start(AGENTIC_VOICE_START_ID, AGENTIC_VOICE_TITLE_ID)) return;
    if (start(VOICE_START_ID, VOICE_TITLE_ID)) return;
    if (framesLeft > 0) requestAnimationFrame(() => attempt(framesLeft - 1));
  }

  if (!document.getElementById(AGENTIC_VOICE_START_ID)
      && !document.getElementById(VOICE_START_ID)) navigate("/");
  attempt(180);
}

// An agentic provider outage should not make a person repeat their speech.
// The legacy VoiceShopping panel accepts the same WAV and prevents this
// cancelable event to report that it took ownership of the recording.
export function requestStandardVoiceFallback(wav) {
  const accepted = !window.dispatchEvent(new CustomEvent(
    STANDARD_VOICE_FALLBACK_EVENT,
    { detail: { wav }, cancelable: true },
  ));
  if (accepted) focusVoiceShopping();
  return accepted;
}
