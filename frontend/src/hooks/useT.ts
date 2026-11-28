import { useContext } from "react";
import { LayoutContext } from "../components/Layout";

// UI labels follow the selected profile language. Locked navigation
// labels keep their own canon at the component level.
export function useT() {
  return useContext(LayoutContext).t;
}
