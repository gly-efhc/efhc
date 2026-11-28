import { useContext } from "react";
import { LayoutContext } from "../components/Layout";

// Descriptions are localized; UI labels/buttons remain English.
export function useTD() {
  return useContext(LayoutContext).td;
}
