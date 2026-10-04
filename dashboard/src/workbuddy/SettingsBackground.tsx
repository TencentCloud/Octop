import { createContext } from "react";
import type { Location } from "react-router-dom";
/** The workspace route remains mounted while settings own the browser address. */
export const SettingsBackgroundContext = createContext<Location | null>(null);
