import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/rubik";
import "@fontsource-variable/nunito-sans";
import App from "./App.jsx";
import "./styles.css";
import "./styles/checkout.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
