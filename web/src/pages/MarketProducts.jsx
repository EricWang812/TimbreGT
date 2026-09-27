import { useEffect, useRef, useState } from "react";
import { createMarketProduct, deleteMarketProduct, getMarketProducts, updateMarketProduct } from "../lib/api.js";
import { formatCents } from "../lib/money.js";

// Seller product management: add, edit, and remove what buyers can buy. The
// storefront reads these same records, so a saved product is on sale at once.
const UNITS = ["oz", "lb", "g", "kg", "fl oz", "mL", "L", "gal", "count"];
const SUGGESTED_CATEGORIES = ["produce", "bakery", "dairy", "seafood", "pantry", "snacks", "drinks", "household", "other"];
const EMPTY = { name: "", price: "", brand: "", category: "", quantity: "", unit: "oz", photoUrl: "" };

function toForm(p) {
  return { name: p.name, price: (p.priceCents / 100).toFixed(2), brand: p.brand ?? "", category: p.category ?? "",
    quantity: p.quantity ?? "", unit: p.unit ?? "oz", photoUrl: p.photoUrl ?? "" };
}

function toBody(form, editing) {
  const measured = String(form.quantity).trim() !== "";
  const body = {
    name: form.name, price: Number(form.price),
    brand: form.brand.trim() || null, category: form.category.trim() || null,
    photoUrl: form.photoUrl.trim() || null,
  };
  if (measured) Object.assign(body, { quantity: Number(form.quantity), unit: form.unit });
  else if (editing) Object.assign(body, { quantity: null, unit: null });   // clearing a size
  return body;
}

function explain(error) {
  if (error.status === 422) {
    if (/photoUrl/i.test(error.message)) return "The photo must be an https:// link or a path starting with /.";
    if (/price/i.test(error.message)) return "Enter a price like 4.99 (no more than two decimal places).";
    return "Check the fields: a name and a price are required, and a size needs both an amount and a unit.";
  }
  if (error.status === 404) return "That product or market is no longer available. Refresh the page.";
  return "The product could not be saved. Try again.";
}

function ProductForm({ initial, categories, submitLabel, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [state, setState] = useState({ status: "idle" });
  const [photoBroken, setPhotoBroken] = useState(false);
  const set = (key) => (e) => { setForm({ ...form, [key]: e.target.value }); if (key === "photoUrl") setPhotoBroken(false); };
  async function submit(event) {
    event.preventDefault();
    if (state.status === "saving") return;
    setState({ status: "saving" });
    try {
      await onSubmit(form);
      setState({ status: "idle" });
    } catch (error) {
      setState({ status: "error", message: explain(error) });
    }
  }
  const photo = form.photoUrl.trim();
  return <form className="product-form" onSubmit={submit}>
    <div className="product-form-grid">
      <label className="form-field product-form-name">Product name<input required maxLength={160} value={form.name} onChange={set("name")} placeholder="Organic Fuji Apples" /></label>
      <label className="form-field">Price (USD)<input required inputMode="decimal" type="number" min="0" step="0.01" value={form.price} onChange={set("price")} placeholder="4.99" /></label>
      <label className="form-field"><span className="field-label">Brand <span className="note">(optional)</span></span><input maxLength={80} value={form.brand} onChange={set("brand")} placeholder="Your brand or farm" /></label>
      <label className="form-field"><span className="field-label">Category <span className="note">(store section)</span></span><input maxLength={60} list="product-categories" value={form.category} onChange={set("category")} placeholder="produce" />
        <datalist id="product-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist></label>
      <fieldset className="product-size">
        <legend>Size <span className="note">(optional)</span></legend>
        <label className="visually-hidden" htmlFor="product-quantity">Amount</label>
        <input id="product-quantity" type="number" min="0" step="any" inputMode="decimal" value={form.quantity} onChange={set("quantity")} placeholder="16" />
        <label className="visually-hidden" htmlFor="product-unit">Unit</label>
        <select id="product-unit" value={form.unit} onChange={set("unit")}>{UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</select>
      </fieldset>
      <label className="form-field product-form-photo"><span className="field-label">Photo link <span className="note">(optional)</span></span>
        <input type="text" pattern="(https://.+|/.+)" inputMode="url" title="An https:// link or a path starting with /" maxLength={2048} value={form.photoUrl} onChange={set("photoUrl")} placeholder="https://example.com/apples.jpg" aria-describedby="photo-hint" /></label>
      <div className="product-preview" aria-live="polite">
        {photo && !photoBroken ? <img src={photo} alt="Photo preview" onError={() => setPhotoBroken(true)} /> : <span>{photoBroken ? "That link did not load an image." : "No photo"}</span>}
      </div>
    </div>
    <p id="photo-hint" className="note">Paste a link to an image (https://…) or a site path such as /products/0013764027053.jpg. The size sets the per-unit price buyers see.</p>
    {state.status === "error" && <p className="message-error" role="alert">{state.message}</p>}
    <div className="product-form-actions">
      <button type="submit" className="btn btn-primary" disabled={state.status === "saving"}>{state.status === "saving" ? "Saving…" : submitLabel}</button>
      {onCancel && <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>}
    </div>
  </form>;
}

export default function MarketProducts({ market }) {
  const [state, setState] = useState({ status: "loading", products: [] });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirming, setConfirming] = useState(null);
  const [message, setMessage] = useState(null);
  const [formKey, setFormKey] = useState(0);
  const addButton = useRef(null);
  useEffect(() => {
    let active = true;
    setState({ status: "loading", products: [] });
    getMarketProducts(market.id).then(
      (products) => { if (active) { setState({ status: "ready", products }); setAdding(products.length === 0); } },
      () => { if (active) setState({ status: "error", products: [] }); },
    );
    return () => { active = false; };
  }, [market.id]);

  const products = state.products;
  const categories = [...new Set([...products.map((p) => p.category).filter(Boolean), ...SUGGESTED_CATEGORIES])];
  const replace = (next) => setState((s) => ({ ...s, products: next(s.products) }));

  async function add(form) {
    const created = await createMarketProduct(market.id, toBody(form, false));
    replace((list) => [...list, created]);
    setMessage(`Added ${created.name}. Buyers can buy it now.`);
    setFormKey((k) => k + 1);   // a fresh, empty form for the next product
  }
  async function save(product, form) {
    const updated = await updateMarketProduct(market.id, product.id, toBody(form, true));
    replace((list) => list.map((p) => (p.id === updated.id ? updated : p)));
    setEditing(null);
    setMessage(`Saved ${updated.name}.`);
  }
  async function remove(product) {
    try {
      await deleteMarketProduct(market.id, product.id);
      replace((list) => list.filter((p) => p.id !== product.id));
      setMessage(`Removed ${product.name}. Past orders keep their record of it.`);
    } catch {
      setMessage(`${product.name} could not be removed. Try again.`);
    } finally { setConfirming(null); }
  }

  if (state.status === "loading") return <p role="status" aria-busy="true">Loading products…</p>;
  if (state.status === "error") return <p className="message-error" role="alert">Unable to load products. Refresh the page to try again.</p>;
  return <section className="stack seller-products" aria-labelledby="products-title">
    <div className="seller-products-head">
      <div>
        <h3 id="products-title">Products <span className="note">({products.length})</span></h3>
        <p className="note">Buyers see these when they choose {market.name} in the store. Changes apply right away.</p>
      </div>
      {!adding && <button ref={addButton} type="button" className="btn btn-primary" onClick={() => { setAdding(true); setMessage(null); }}>+ Add product</button>}
    </div>
    <p className="purchase-message" role="status">{message}</p>

    {adding && <section className="seller-panel" aria-labelledby="add-title">
      <h4 id="add-title">{products.length ? "Add a product" : "Add your first product"}</h4>
      <ProductForm key={formKey} initial={EMPTY} categories={categories} submitLabel="Add product" onSubmit={add}
        onCancel={products.length ? () => { setAdding(false); setTimeout(() => addButton.current?.focus()); } : null} />
    </section>}

    {!products.length ? <p className="note">No products yet. Add one above and it appears in the store.</p> : <ul className="seller-product-list">
      {products.map((product) => <li key={product.id} className="seller-product">
        {editing === product.id ? <section className="seller-panel seller-edit" aria-label={`Edit ${product.name}`}>
          <ProductForm initial={toForm(product)} categories={categories} submitLabel="Save changes" onSubmit={(form) => save(product, form)} onCancel={() => setEditing(null)} />
        </section> : <>
          {product.photoUrl ? <img className="seller-product-photo" src={product.photoUrl} alt="" width="72" height="72" loading="lazy" /> : <span className="seller-product-photo" aria-hidden="true" />}
          <div className="seller-product-info">
            {product.brand && <p className="note">{product.brand}</p>}
            <p className="seller-product-name">{product.name}</p>
            <p className="note">{[product.category ?? "no category", product.quantity ? `${product.quantity} ${product.unit}` : null].filter(Boolean).join(" · ")}</p>
          </div>
          <p className="seller-product-price">{formatCents(product.priceCents)}</p>
          <div className="seller-product-actions">
            {confirming === product.id ? <>
              <span className="note">Remove from the store?</span>
              <button type="button" className="btn btn-danger" onClick={() => remove(product)}>Yes, remove</button>
              <button type="button" className="btn btn-secondary" onClick={() => setConfirming(null)}>Keep</button>
            </> : <>
              <button type="button" className="btn btn-secondary" onClick={() => { setEditing(product.id); setMessage(null); }} aria-label={`Edit ${product.name}`}>Edit</button>
              <button type="button" className="btn btn-secondary" onClick={() => setConfirming(product.id)} aria-label={`Remove ${product.name}`}>Remove</button>
            </>}
          </div>
        </>}
      </li>)}
    </ul>}
  </section>;
}
