// The cart lives in the browser as {productId: quantity}. It holds no prices:
// the merchant prices every cart server-side (api/cart.py).
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

// Mirrors api/config.py MAX_QUANTITY; the server enforces it regardless.
export const MAX_QUANTITY = 20;
const STORAGE_KEY = "seaside-cart";

const CartContext = createContext(null);

function load() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch (err) {
    console.warn("could not restore cart from sessionStorage", err);
    return {};
  }
}

export function CartProvider({ children }) {
  const [items, setItems] = useState(load);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch (err) {
      console.warn("could not save cart to sessionStorage", err);  // a convenience only
    }
  }, [items]);

  const setQuantity = useCallback((productId, quantity) => {
    setItems((prev) => {
      const next = { ...prev };
      if (quantity <= 0) delete next[productId];
      else next[productId] = Math.min(quantity, MAX_QUANTITY);
      return next;
    });
  }, []);

  const value = useMemo(() => {
    const lines = Object.entries(items).map(([productId, quantity]) => ({ productId, quantity }));
    return {
      lines,
      count: lines.reduce((sum, line) => sum + line.quantity, 0),
      quantityOf: (productId) => items[productId] ?? 0,
      add: (productId) => setQuantity(productId, (items[productId] ?? 0) + 1),
      setQuantity,
      clear: () => setItems({}),
    };
  }, [items, setQuantity]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const cart = useContext(CartContext);
  if (!cart) throw new Error("useCart must be used inside <CartProvider>");
  return cart;
}

export function itemCountText(count) {
  return count === 1 ? "1 item in cart" : `${count} items in cart`;
}
