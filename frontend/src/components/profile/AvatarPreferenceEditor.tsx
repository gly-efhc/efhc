import React, { useEffect, useRef, useState } from "react";
import { useT } from "../../hooks/useT";
import { useAvatarPreference } from "../../queries/useAvatarPreference";
import {
  AVATAR_ICON_IDS, normalizeAvatarHttpsUrl,
  type AvatarPreference, type AvatarIcon,
} from "../../lib/avatarPreference";
import { EnergyVariantIcon } from "../icons/EnergyVariantIcon";

export function AvatarPreferenceEditor() {
  const t = useT();
  const { owner, preferenceQuery, sourcesQuery, save } = useAvatarPreference();
  const envelope = preferenceQuery.data;
  const [draftUrl, setDraftUrl] = useState("");
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [validatedUrl, setValidatedUrl] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const checkGeneration = useRef(0);
  const activeOwner = useRef(owner);
  const hydratedOwner = useRef("");
  activeOwner.current = owner;
  const checkedImage = useRef<HTMLImageElement | null>(null);
  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    checkGeneration.current += 1;
    if (previewTimer.current) clearTimeout(previewTimer.current);
    if (checkedImage.current) { checkedImage.current.onload = null; checkedImage.current.onerror = null; }
  }, []);
  useEffect(() => {
    setDraftUrl(""); setPreviewStatus("idle"); setValidatedUrl(null); setMessage("");
    checkGeneration.current += 1;
    hydratedOwner.current = "";
    if (previewTimer.current) clearTimeout(previewTimer.current);
    if (checkedImage.current) { checkedImage.current.onload = null; checkedImage.current.onerror = null; checkedImage.current.removeAttribute("src"); }
  }, [owner]);
  useEffect(() => {
    if (!owner || !envelope || hydratedOwner.current === owner) return;
    hydratedOwner.current = owner;
    if (envelope.preference.selection.kind === "url") {
      setDraftUrl(envelope.preference.selection.url);
    }
  }, [owner, envelope]);

  function editUrl(value: string) {
    checkGeneration.current += 1;
    if (previewTimer.current) clearTimeout(previewTimer.current);
    if (checkedImage.current) { checkedImage.current.onload = null; checkedImage.current.onerror = null; }
    setDraftUrl(value); setPreviewStatus("idle"); setValidatedUrl(null); setMessage("");
  }
  function preview() {
    const url = normalizeAvatarHttpsUrl(draftUrl);
    if (!url) { setPreviewStatus("error"); setMessage(t("profile.avatar_url_invalid")); return; }
    const generation = ++checkGeneration.current;
    setPreviewStatus("loading"); setValidatedUrl(null); setMessage("");
    const img = new Image(); checkedImage.current = img; img.referrerPolicy = "no-referrer";
    const finish = (ok: boolean) => {
      if (generation !== checkGeneration.current) return;
      if (previewTimer.current) clearTimeout(previewTimer.current);
      img.onload = null; img.onerror = null;
      setPreviewStatus(ok ? "ready" : "error"); setValidatedUrl(ok ? url : null);
      if (!ok) setMessage(t("profile.avatar_url_unavailable"));
    };
    img.onload = () => finish(img.naturalWidth > 0 && img.naturalHeight > 0);
    img.onerror = () => finish(false);
    previewTimer.current = setTimeout(() => finish(false), 10_000);
    img.src = url;
  }
  async function persist(preference: AvatarPreference) {
    if (!envelope || !owner) return;
    setMessage("");
    try {
      const ownerAtStart = owner;
      await save.mutateAsync({ preference, expectedRevision: envelope.revision, ownerAtStart });
      if (activeOwner.current === ownerAtStart) setMessage(t("profile.avatar_saved"));
    } catch {
      if (activeOwner.current === owner) setMessage(t("profile.avatar_save_failed"));
    }
  }
  function chooseIcon(icon: AvatarIcon) {
    if (!envelope) return;
    const pref = envelope.preference;
    // One picker owns both the primary icon and the image-error fallback.
    void persist({ ...pref, selection: { kind: "icon" }, fallbackIcon: icon });
  }
  const active = envelope?.preference;
  const availablePhotos = (sourcesQuery.data?.items ?? []).filter(
    (source) => source.status === "available" && Boolean(source.avatarUrl),
  );
  const canSaveUrl = Boolean(validatedUrl && validatedUrl === normalizeAvatarHttpsUrl(draftUrl) && previewStatus === "ready" && !save.isPending);
  return (
    <div className="efhc-profile-avatar-editor" data-avatar-preference="global-id-server">
      <div aria-live="polite" className="text-xs text-[color:var(--tg-hint)]">
        {owner && preferenceQuery.isError ? t("profile.avatar_save_failed") : null}
        {owner && !envelope && !preferenceQuery.isError ? t("profile.avatar_loading") : null}
        {!owner ? t("profile.avatar_login_required") : null}
      </div>
      {availablePhotos.length > 0 ? <div className="efhc-profile-avatar-settings-group" role="group" aria-label={t("profile.avatar_linked_accounts")}>
        {availablePhotos.map((source) => (
          <button key={source.identityId} type="button" className="efhc-profile-avatar-social"
            aria-pressed={active?.selection.kind === "provider" && active.selection.identityId === source.identityId}
            disabled={!envelope || save.isPending || (source.status !== "available" && !(active?.selection.kind === "provider" && active.selection.identityId === source.identityId))}
            onClick={() => active && void persist({ ...active, selection: { kind: "provider", identityId: source.identityId } })}>
            {source.avatarUrl && source.status === "available" ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={source.avatarUrl} alt="" referrerPolicy="no-referrer" />
            ) : <span aria-hidden="true">—</span>}
            <span>{source.label}: {source.status === "unsupported" ? t("profile.avatar_no_provider_photo") : source.status === "no_photo" ? t("profile.avatar_no_photo") : ""}</span>
          </button>
        ))}
      </div> : null}
      <div className="efhc-profile-avatar-settings-group">
        <div className="efhc-profile-avatar-settings-label">{t("profile.avatar_energy_presets")}</div>
        <div className="efhc-profile-avatar-preset-grid" role="group" aria-label={t("profile.avatar_energy_presets")}>
          {AVATAR_ICON_IDS.map((icon) => <button key={icon} type="button" className="efhc-profile-avatar-preset" aria-label={icon}
            aria-pressed={active?.fallbackIcon === icon}
            disabled={!envelope || save.isPending} onClick={() => chooseIcon(icon)}>
            <EnergyVariantIcon variant={icon} size={26} />
          </button>)}
        </div>

      </div>
      <div className="efhc-profile-avatar-settings-group">
        <label className="efhc-profile-avatar-settings-label" htmlFor="efhc-avatar-external-url">{t("profile.avatar_url_heading")}</label>
        <div className="text-xs text-[color:var(--tg-hint)]">{t("profile.avatar_url_hint")}</div>
        <input id="efhc-avatar-external-url" className="efhc-profile-avatar-url-input" type="url"
          value={draftUrl} disabled={save.isPending || !envelope}
          onChange={(e) => editUrl(e.target.value)} placeholder="https://" />
        <div className="efhc-profile-avatar-url-actions">
          <button type="button" onClick={preview} disabled={!envelope || save.isPending || previewStatus === "loading"}>{t("profile.avatar_preview")}</button>
          <button type="button" disabled={!canSaveUrl} onClick={() => active && validatedUrl && void persist({ ...active, selection: { kind: "url", url: validatedUrl } })}>{t("profile.avatar_save")}</button>
          {active?.selection.kind === "url" ? <button type="button" disabled={save.isPending} onClick={() => void persist({ ...active, selection: { kind: "icon" } })}>{t("profile.avatar_remove_url")}</button> : null}
        </div>
        {previewStatus === "ready" && validatedUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={validatedUrl} alt={t("profile.avatar_preview")} referrerPolicy="no-referrer" className="efhc-profile-avatar-url-preview" onError={() => { setValidatedUrl(null); setPreviewStatus("error"); }} />
        ) : null}
        <div aria-live="polite" className="text-xs">{message}</div>
      </div>
    </div>
  );
}
