import React from "react";

// Isolate the physical unit from uppercase KPI captions without changing them.
export function EnergyUnitText({ text }: { text: string }) {
  return <>{text.split(/(kwh(?:\/[sсc])?)/gi).map((part, index) => /^kwh(?:\/[sсc])?$/i.test(part)
    ? <span key={index} data-energy-unit={part.includes("/") ? "kWh/s" : "kWh"} style={{ display: "inline", textTransform: "none", font: "inherit", letterSpacing: "inherit" }}>{part.includes("/") ? "kWh/s" : "kWh"}</span>
    : part)}</>;
}
