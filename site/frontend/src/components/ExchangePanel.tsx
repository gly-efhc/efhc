// Guard marker: Exchange page is kWh -> EFHC only.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {useOwnerDraft} from "../hooks/useOwnerDraft";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { useT } from "../hooks/useT";
import { onTelegramViewportChanged } from "../lib/telegram";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";
import {
  fromScaledBigint,
  toScaledBigintDown,
} from "../lib/format";

type Props = {
  maxKwh: string;
  onExchange: (amountKwh: string) => Promise<void>;
  pending?: boolean;
};

function validDecimal(raw: string): boolean {
  const value = raw.trim();
  if (!value) return false;
  if (value.includes("e") || value.includes("E")) return false;
  if (value.includes("-")) return false;
  return /^\d+(\.\d{0,8})?$/.test(value);
}

function sanitizeAmountInput(raw: string): string {
  const cleaned = raw.replace(/,/g, ".").replace(/\s+/g, "");
  let result = "";
  let hasDot = false;
  let decimals = 0;
  for (const char of cleaned) {
    if (char >= "0" && char <= "9") {
      if (hasDot) {
        if (decimals >= 8) continue;
        decimals += 1;
      }
      result += char;
      continue;
    }
    if (char === "." && !hasDot) {
      hasDot = true;
      result += result ? "." : "0.";
    }
  }
  return result;
}

export function ExchangePanel(props: Props) {
  const t = useT();
  const maxScaled = useMemo(() => {
    return toScaledBigintDown(props.maxKwh || "0", 8);
  }, [props.maxKwh]);
  const [amount, setAmount] = useOwnerDraft("exchange.amount","0.00000000");
  const amountInputRef = useRef<HTMLInputElement | null>(null);
  const cardSurface = useInterfaceVariantSurface<HTMLDivElement>("XC", { registerDots: false, interactive: false });
  const actionSurface = useInterfaceVariantSurface<HTMLDivElement>("XA", { registerDots: false, interactive: false });

  const amountIsValid = useMemo(() => {
    return validDecimal(amount);
  }, [amount]);

  const amountScaled = useMemo(() => {
    if (!amountIsValid) return 0n;
    return toScaledBigintDown(amount, 8);
  }, [amount, amountIsValid]);

  const normalizedAmount = useMemo(() => {
    return fromScaledBigint(amountScaled, 8);
  }, [amountScaled]);

  const overMax = useMemo(() => {
    return amountScaled > maxScaled;
  }, [amountScaled, maxScaled]);

  const disabled = useMemo(() => {
    if (props.pending) return true;
    if (!amountIsValid) return true;
    if (amountScaled <= 0n) return true;
    return overMax;
  }, [props.pending, amountIsValid, amountScaled, overMax]);

  const helperText = useMemo(() => {
    if (!amountIsValid) return t("exchange.amount_invalid_detail");
    if (overMax) return t("exchange.amount_over_available");
    return "";
  }, [amountIsValid, overMax, t]);

  function setMax() {
    setAmount(fromScaledBigint(maxScaled, 8));
  }

  function onAmountChange(value: string) {
    setAmount(sanitizeAmountInput(value));
  }

  useEffect(() => {
    let frameOne = 0;
    let frameTwo = 0;

    const recoverFocusedAmount = () => {
      const input = amountInputRef.current;
      if (!input || document.activeElement !== input) return;

      if (frameOne) window.cancelAnimationFrame(frameOne);
      if (frameTwo) window.cancelAnimationFrame(frameTwo);

      frameOne = window.requestAnimationFrame(() => {
        frameTwo = window.requestAnimationFrame(() => {
          if (document.activeElement !== input) return;

          const main = input.closest<HTMLElement>(".efhc-game-shell_main");
          const surface = actionSurface.ref.current;
          const submit = surface?.querySelector<HTMLElement>(
            '[data-exchange-submit-action="true"]',
          );
          if (!main || !submit) return;

          const mainRect = main.getBoundingClientRect();
          const nav = document.querySelector<HTMLElement>(".efhc-game-nav");
          const navTop = nav?.getBoundingClientRect().top ?? mainRect.bottom;
          const visibleTop = mainRect.top + 12;
          const visibleBottom = Math.min(mainRect.bottom, navTop) - 12;
          const inputRect = input.getBoundingClientRect();
          const submitRect = submit.getBoundingClientRect();

          let delta = 0;
          if (submitRect.bottom > visibleBottom) {
            delta = submitRect.bottom - visibleBottom;
          }

          const inputTopAfterScroll = inputRect.top - delta;
          if (inputTopAfterScroll < visibleTop) {
            delta -= visibleTop - inputTopAfterScroll;
          }

          if (Math.abs(delta) > 0.5) {
            main.scrollTop += delta;
          }
        });
      });
    };

    const offTelegramViewport = onTelegramViewportChanged(
      recoverFocusedAmount,
    );
    window.visualViewport?.addEventListener("resize", recoverFocusedAmount);

    return () => {
      offTelegramViewport();
      window.visualViewport?.removeEventListener(
        "resize",
        recoverFocusedAmount,
      );
      if (frameOne) window.cancelAnimationFrame(frameOne);
      if (frameTwo) window.cancelAnimationFrame(frameTwo);
    };
  }, []);

  return (
    <Card
      ref={cardSurface.ref}
      {...cardSurface.handlers}
      title={t("exchange.title")}
      className="efhc-exchange-card-variant"
      data-xc={cardSurface.variant}
    >
      <div
        className="efhc-exchange-panel"
        data-exchange-boundary="kwh-to-efhc-only"
        data-exchange-rate="1-kwh-1-efhc"
        data-exchange-amount-polish="1287"
      >
        <div className="text-sm efhc-text-muted">
          {t("exchange.input_instruction")}
        </div>
        <div
          ref={actionSurface.ref}
          {...actionSurface.handlers}
          className="efhc-exchange-action-surface"
          data-xa={actionSurface.variant}
        >
        <div className="efhc-exchange-canonical-row">
          <div>
            <div className="text-xs efhc-text-muted2">
              {t("exchange.available_for_exchange")}
            </div>
            <div className="mt-1 font-semibold tabular-nums">
              {fromScaledBigint(maxScaled, 8)}
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={setMax}
            data-exchange-max-action="true"
          >
            {t("exchange.max")}
          </Button>
        </div>
        <label className="efhc-exchange-input-group">
          <span className="text-xs efhc-text-muted2">
            {t("exchange.amount_kwh_label")}
          </span>
          <input
            ref={amountInputRef}
            className="efhc-input w-full"
            value={amount}
            onChange={(e) => onAmountChange(e.target.value)}
            inputMode="decimal"
            placeholder="0.00000000"
            aria-invalid={overMax || !amountIsValid}
            aria-describedby={helperText ? "efhc-exchange-amount-helper" : undefined}
            aria-label={t("exchange.amount_kwh_label")}
            data-exchange-amount-input="kwh"
          />
        </label>
        <div
          className="efhc-exchange-preview-row"
          data-exchange-preview="one-to-one"
        >
          <span>{t("exchange.receive_efhcm")}</span>
          <strong className="tabular-nums">
            {normalizedAmount}
          </strong>
        </div>
        {helperText ? (
          <div
            id="efhc-exchange-amount-helper"
            className="efhc-exchange-helper efhc-exchange-helper--warning"
            data-exchange-amount-helper="true"
          >
            {helperText}
          </div>
        ) : null}
        <Button
          className="w-full efhc-theme03-cta"
          data-exchange-submit-action="true"
          onClick={() => props.onExchange(normalizedAmount)}
          disabled={disabled}
        >
          {props.pending
            ? t("exchange.processing")
            : t("exchange.action_exchange_kwh")}
        </Button>
        </div>
      </div>
    </Card>
  );
}
