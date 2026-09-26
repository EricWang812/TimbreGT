import { useState } from "react";
import { useCart } from "../lib/cart.jsx";
import { BagIcon, MicIcon, WavesIcon } from "./Icons.jsx";
import { focusVoiceShopping } from "./jump.js";

export default function SiteHeader({ onOpenCart }) {
  const { count } = useCart();
  // A5: the badge bumps only when the count goes up (never on first render,
  // never on a removal). Changing the key remounts the badge, which replays
  // the CSS animation without listening for animationend.
  const [badge, setBadge] = useState({ count, bumps: 0 });
  if (badge.count !== count) {
    setBadge({ count, bumps: count > badge.count ? badge.bumps + 1 : badge.bumps });
  }

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <a className="brand" href="#/"><WavesIcon size={28} /> Seaside Market</a>
        <div className="header-actions">
          {/* A button, not a link: it moves focus on this page and never navigates.
              Below 600px it is icon-only; the text stays as its accessible name. */}
          <button type="button" className="header-voice" onClick={focusVoiceShopping}>
            <MicIcon size={20} /> <span className="header-voice-text">Shop by voice</span>
          </button>
          <button type="button" className="btn btn-primary cart-button" onClick={onOpenCart} aria-haspopup="dialog">
            <BagIcon size={22} />
            Cart
            <span className="cart-count" key={badge.bumps} data-bump={badge.bumps > 0 ? "" : undefined}>{count}</span>
            <span className="visually-hidden">{count === 1 ? "item" : "items"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
