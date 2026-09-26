// The bank's own icons. Code under src/issuer/ imports nothing from the
// storefront, as if it were served from the bank's origin (ADR 2).
function Icon({ size = 24, children }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export const BankIcon = (p) => (
  <Icon {...p}>
    <path d="M3 21h18" />
    <path d="M5 17V10M9.5 17V10M14.5 17V10M19 17V10" />
    <path d="M12 3 3 8h18l-9-5Z" />
  </Icon>
);

export const ShieldIcon = (p) => (
  <Icon {...p}>
    <path d="M12 3 4 6v6c0 4.5 3.4 7.8 8 9 4.6-1.2 8-4.5 8-9V6l-8-3Z" />
    <path d="m9 12 2 2 4-4" />
  </Icon>
);

export const CheckIcon = (p) => (
  <Icon {...p}>
    <path d="M20 6 9 17l-5-5" />
  </Icon>
);
