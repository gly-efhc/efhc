import React, { useEffect, useState } from "react";
import type { AvatarIcon, ResolvedAvatar } from "../../lib/avatarPreference";
import { EnergyVariantIcon } from "../icons/EnergyVariantIcon";

function Icon({ variant, size }: { variant: AvatarIcon; size: number }) {
  return (
    <span className="efhc-profile-avatar-energy" aria-hidden="true">
      <span className="efhc-energy-stage_coin" data-ei={variant}>
        <EnergyVariantIcon variant={variant} size={size} />
      </span>
    </span>
  );
}
function Photo(props: { value: Extract<ResolvedAvatar, { kind: "image" }>; size: number; alt: string }) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    if (state !== "loading") return;
    const timeout = window.setTimeout(() => setState("error"), 10_000);
    return () => window.clearTimeout(timeout);
  }, [state]);
  const { src, fit, fallback } = props.value;
  return (
    <span className="efhc-unified-avatar" style={{ display: "inline-grid", width: props.size, height: props.size }}>
      {state !== "ready" ? <span style={{ gridArea: "1 / 1" }}><Icon variant={fallback} size={props.size} /></span> : null}
      {state !== "error" ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={props.alt} referrerPolicy="no-referrer" draggable={false}
          className="efhc-profile-avatar-image" data-avatar-fit={fit}
          width={props.size} height={props.size}
          style={{ gridArea: "1 / 1", width: "100%", height: "100%", borderRadius: "50%",
            visibility: state === "ready" ? "visible" : "hidden",
            objectFit: fit === "symbol" ? "contain" : "cover",
            objectPosition: fit === "symbol" ? "center" : "50% 38%",
            padding: fit === "symbol" ? "12%" : 0, boxSizing: "border-box" }}
          onLoad={(e) => setState(e.currentTarget.naturalWidth > 0 && e.currentTarget.naturalHeight > 0 ? "ready" : "error")}
          onError={() => setState("error")} />
      ) : null}
    </span>
  );
}
export function UnifiedAvatar(props: { value: ResolvedAvatar; size?: number; alt?: string; attempt?: number }) {
  const size = props.size ?? 28;
  if (props.value.kind === "icon") return <Icon variant={props.value.icon} size={size} />;
  return <Photo key={`${props.value.key}:${props.attempt ?? 0}`} value={props.value} size={size} alt={props.alt ?? ""} />;
}
