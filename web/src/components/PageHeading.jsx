import { useEffect, useRef } from "react";
import { shouldFocusHeading } from "../lib/router.js";

// After an in-app navigation, focus lands on the new page's heading so it is
// announced and the next Tab starts from the new content.
export default function PageHeading({ children }) {
  const ref = useRef(null);
  useEffect(() => {
    if (shouldFocusHeading()) ref.current.focus();
  }, []);
  return <h1 ref={ref} tabIndex={-1}>{children}</h1>;
}
