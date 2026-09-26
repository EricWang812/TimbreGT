// In-page jumps for the store (aisle chips, the header's "Shop by voice" link).
// A plain href="#pantry" would be read as a route by the hash router, so every
// jump is handled in JavaScript: scroll, then move focus to the target.
import { navigate } from "../lib/router.js";

// Stable ids so other store components (the header link, the cart drawer's
// empty state) can reach the voice panel without importing it.
export const VOICE_START_ID = "voice-shopping-start";
export const VOICE_TITLE_ID = "voice-shopping-title";

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
