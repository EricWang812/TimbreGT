// One polite and one assertive live region for the whole app, instead of a
// live region per widget competing for the screen reader (CLAUDE.md §13.1).
import { createContext, useCallback, useContext, useRef, useState } from "react";

const AnnounceContext = createContext(null);

export function AnnouncerProvider({ children }) {
  const [polite, setPolite] = useState("");
  const [urgent, setUrgent] = useState("");
  const frames = useRef({ polite: 0, urgent: 0 });  // one per region, so neither cancels the other

  const announce = useCallback((message, { assertive = false } = {}) => {
    const key = assertive ? "urgent" : "polite";
    const set = assertive ? setUrgent : setPolite;
    // Clear first so an identical message is announced again.
    set("");
    cancelAnimationFrame(frames.current[key]);
    frames.current[key] = requestAnimationFrame(() => set(message));
  }, []);

  return (
    <AnnounceContext.Provider value={announce}>
      {children}
      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">{polite}</div>
      <div className="visually-hidden" role="alert" aria-live="assertive" aria-atomic="true">{urgent}</div>
    </AnnounceContext.Provider>
  );
}

export function useAnnounce() {
  const announce = useContext(AnnounceContext);
  if (!announce) throw new Error("useAnnounce must be used inside <AnnouncerProvider>");
  return announce;
}
