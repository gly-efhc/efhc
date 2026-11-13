import React, { useEffect, useRef, useState } from "react";

import { SUPPORTED_LANGS, type Lang } from "../../lib/i18n";
import { languageDisplayName, languageFlag } from "../../lib/languagePresentation";

type Props = {
  value: Lang;
  label: string;
  showLabel?: boolean;
  profileSurface?: boolean;
  getLabel: (lang: Lang) => string;
  onChange: (lang: Lang) => void;
};

export function CompactLanguagePicker(props: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() =>
    Math.max(0, SUPPORTED_LANGS.indexOf(props.value)),
  );
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const activeOptionRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    setActiveIndex(Math.max(0, SUPPORTED_LANGS.indexOf(props.value)));
    activeOptionRef.current?.focus();
  }, [open, props.value]);

  return (
    <div className="efhc-compact-language-picker">
      <button
        ref={triggerRef}
        type="button"
        className={props.profileSurface ? "efhc-compact-language-picker_button source-profile-language-button" : "efhc-compact-language-picker_button"}
        aria-haspopup="listbox"
        aria-label={props.label}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {props.profileSurface ? (
          <>
            <span aria-hidden="true">{languageFlag(props.value)}</span>
            <strong>{languageDisplayName(props.value, props.getLabel(props.value))}</strong>
            <span aria-hidden="true">▾</span>
          </>
        ) : (
          <>
            {props.showLabel !== false ? <span className="efhc-compact-language-picker_label">{props.label}</span> : null}
            <span className="efhc-compact-language-picker_current">
              <span aria-hidden="true">{languageFlag(props.value)}</span>
              <strong>{languageDisplayName(props.value, props.getLabel(props.value))}</strong>
              <span aria-hidden="true">▾</span>
            </span>
          </>
        )}
      </button>
      {open ? (
        <div
          className={props.profileSurface ? "efhc-compact-language-picker_menu source-profile-language-menu" : "efhc-compact-language-picker_menu"}
          role="listbox"
          aria-label={props.label}
        >
          {SUPPORTED_LANGS.map((lang, index) => {
            const selected = lang === props.value;
            const focusActive = index === activeIndex;
            return (
              <button
                key={lang}
                ref={(node) => {
                  optionRefs.current[index] = node;
                  if (selected) activeOptionRef.current = node;
                }}
                type="button"
                role="option"
                aria-selected={selected}
                tabIndex={focusActive ? 0 : -1}
                className={props.profileSurface ? "efhc-compact-language-picker_option source-profile-language-option" : "efhc-compact-language-picker_option"}
                data-active={selected ? "true" : "false"}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    props.onChange(lang);
                    setOpen(false);
                    window.requestAnimationFrame(() => triggerRef.current?.focus());
                    return;
                  }
                  if (event.key === "Escape") {
                    event.preventDefault();
                    setOpen(false);
                    window.requestAnimationFrame(() => triggerRef.current?.focus());
                    return;
                  }
                  if (event.key === "Home" || event.key === "End") {
                    event.preventDefault();
                    const nextIndex = event.key === "Home" ? 0 : SUPPORTED_LANGS.length - 1;
                    setActiveIndex(nextIndex);
                    optionRefs.current[nextIndex]?.focus();
                    return;
                  }
                  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
                  event.preventDefault();
                  const direction = event.key === "ArrowDown" ? 1 : -1;
                  const nextIndex = Math.max(
                    0,
                    Math.min(SUPPORTED_LANGS.length - 1, index + direction),
                  );
                  setActiveIndex(nextIndex);
                  optionRefs.current[nextIndex]?.focus();
                }}
                onClick={() => {
                  props.onChange(lang);
                  setOpen(false);
                }}
              >
                <span aria-hidden="true">{languageFlag(lang)}</span>
                <span>{languageDisplayName(lang, props.getLabel(lang))}</span>
                {selected ? <span aria-hidden="true">✓</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
