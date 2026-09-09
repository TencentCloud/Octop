import { createRoot } from "react-dom/client";
import { initDesktopI18n } from "./i18n";
import ShellApp from "./ShellApp";
import "./shell.css";

window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

void initDesktopI18n().then(() => {
  const root = document.getElementById("root");
  if (!root) return;
  createRoot(root).render(<ShellApp />);
});
