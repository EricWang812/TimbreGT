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

  // Functional updates: two taps faster than a re-render both count
  // (reading `items` from this render would lose one).
  const adjust = useCallback((productId, delta) => {
    setItems((prev) => {
      const next = { ...prev };
      const quantity = Math.min((prev[productId] ?? 0) + delta, MAX_QUANTITY);
      if (quantity <= 0) delete next[productId];
      else next[productId] = quantity;
      return next;
    });
  }, []);

  // Apply a server-prepared cart in one state update. Validate every line
  // first so malformed agent output can never partially change the cart.
  const replaceLines = useCallback((lines) => {
    if (!Array.isArray(lines)) throw new Error("The prepared cart was invalid. Your cart was not changed.");
    const next = {};
    for (const line of lines) {
      const productId = line.product_id ?? line.productId;
      const quantity = line.quantity;
      if (typeof productId !== "string" || !Number.isInteger(quantity) || quantity < 1 || quantity > MAX_QUANTITY) {
        throw new Error("The prepared cart was invalid. Your cart was not changed.");
      }
      next[productId] = quantity;
    }
    setItems(next);
  }, []);

  const value = useMemo(() => {
    const lines = Object.entries(items).map(([productId, quantity]) => ({ productId, quantity }));
    return {
      lines,
      count: lines.reduce((sum, line) => sum + line.quantity, 0),
      quantityOf: (productId) => items[productId] ?? 0,
      add: (productId) => adjust(productId, 1),
      adjust,
      setQuantity,
      replaceLines,
      clear: () => setItems({}),
    };
  }, [items, setQuantity, adjust, replaceLines]);

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
