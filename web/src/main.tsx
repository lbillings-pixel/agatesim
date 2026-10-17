import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { installRadioKeys } from "./lib/radiogroup";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");
installRadioKeys();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
