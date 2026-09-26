import { useCart } from "../lib/cart.jsx";
import { BagIcon, WavesIcon } from "./Icons.jsx";

export default function SiteHeader({ onOpenCart }) {
  const { count } = useCart();
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <a className="brand" href="#/"><WavesIcon size={28} /> Seaside Market</a>
        <button type="button" className="btn btn-primary" onClick={onOpenCart} aria-haspopup="dialog">
          <BagIcon size={22} />
          Cart
          <span className="cart-count">{count}</span>
          <span className="visually-hidden">{count === 1 ? "item" : "items"}</span>
        </button>
      </div>
    </header>
  );
}
