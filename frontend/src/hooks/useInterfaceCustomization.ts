import { useContext } from "react";
import { InterfaceCustomizationContext } from
  "../components/interface-settings/InterfaceCustomizationProvider";

export function useInterfaceCustomization() {
  return useContext(InterfaceCustomizationContext);
}
