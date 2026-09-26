import VoiceShopping from "../components/VoiceShopping.jsx";
import PageHeading from "../components/PageHeading.jsx";
import { PlusIcon } from "../components/Icons.jsx";
import { itemCountText, MAX_QUANTITY, useCart } from "../lib/cart.jsx";
import { useAnnounce } from "../lib/announce.jsx";
import { formatCents } from "../lib/money.js";

// Display sections, in order. Seafood leads: it is a seaside market. Small
// catalog categories are merged so no section is a lone card in a wide row.
const SECTIONS = [
  ["sea", "From the sea", ["seafood"]],
  ["fresh", "Fresh and dairy", ["produce", "bakery", "dairy"]],
  ["drinks", "Drinks", ["drinks"]],
  ["pantry", "Pantry and snacks", ["pantry", "snacks"]],
];

function ProductCard({ product }) {
  const cart = useCart();
  const announce = useAnnounce();
  const inCart = cart.quantityOf(product.id);
  const atLimit = inCart >= MAX_QUANTITY;

  function add() {
    cart.add(product.id);
    announce(`Added ${product.brand} ${product.name}. ${itemCountText(cart.count + 1)}.`);
  }

  return (
    <li>
      <article className="product-card" aria-labelledby={`product-${product.id}`}>
        {/* alt="" because the brand and name are the adjacent text; describing
            the photo again would make screen readers repeat every product. */}
        <img className="product-photo" src={product.image_url} alt="" width="240" height="240"
          loading="lazy" decoding="async" />
        <div className="product-body">
          <p className="product-brand">{product.brand}</p>
          <h3 id={`product-${product.id}`}>{product.name}</h3>
          <p className="product-size">{product.size}</p>
          <div className="product-footer">
            <span className="price">{formatCents(product.price_cents)}</span>
            <button type="button" className="btn btn-primary" onClick={add} disabled={atLimit}
              aria-label={`Add to cart: ${product.brand} ${product.name}`}>
              <PlusIcon size={20} /> Add
            </button>
          </div>
          {inCart > 0 && <p className="in-cart-note">{inCart} in cart</p>}
        </div>
      </article>
    </li>
  );
}

export default function Shop({ catalog }) {
  const groups = SECTIONS
    .map(([key, label, categories]) => [key, label, catalog.products.filter((p) => categories.includes(p.category))])
    .filter(([, , items]) => items.length > 0);
  const known = new Set(SECTIONS.flatMap(([, , categories]) => categories));
  const other = catalog.products.filter((p) => !known.has(p.category));
  if (other.length) groups.push(["other", "More", other]);

  return (
    <>
      <div className="page-intro">
        <PageHeading>Shop the market</PageHeading>
        <p>Fresh from the coast. Add items by voice, with a tap, or with the keyboard.</p>
      </div>

      {catalog.status === "loading" && <p aria-busy="true">Loading products…</p>}
      {catalog.status === "error" && (
        <div className="stack">
          <p className="message-error" role="alert">The product list could not load.</p>
          <p><button type="button" className="btn btn-secondary" onClick={catalog.reload}>Try again</button></p>
        </div>
      )}

      {catalog.status !== "loading" && catalog.products.length > 0 && <VoiceShopping products={catalog.products} />}

      {groups.map(([key, label, items]) => (
        <section key={key} className="category" aria-labelledby={`category-${key}`}>
          <h2 id={`category-${key}`}>{label}</h2>
          <ul className="product-grid">
            {items.map((p) => <ProductCard key={p.id} product={p} />)}
          </ul>
        </section>
      ))}
    </>
  );
}
