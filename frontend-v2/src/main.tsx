import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/base.css";
import App from "./App";
import { applyPrefsToDocument, usePrefs } from "./state/prefs";

applyPrefsToDocument(usePrefs.getState());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
