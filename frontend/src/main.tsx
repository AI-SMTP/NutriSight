import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import "./styles/tokens.css";
import "./styles/global.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("#root 요소가 없습니다");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
