import React from "react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { useT } from "../../hooks/useT";

export type AdminPromptField = {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "number" | "textarea";
};

export function AdminPromptModal(props: {
  open: boolean;
  title: string;
  submitLabel?: string;
  fields: AdminPromptField[];
  values: Record<string, string>;
  busy?: boolean;
  submitDisabled?: boolean;
  onChange: (key: string, value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
  dataAdminPromptMarker?: string;
}) {
  const t = useT();
  return (
    <Modal
      open={props.open}
      onClose={props.onClose}
      closeDisabled={props.busy}
      title={props.title}
    >
      <div
        className="grid gap-3"
        data-admin-primitive="modal"
        data-admin-prompt-marker={props.dataAdminPromptMarker || undefined}
      >
        {props.fields.map((field) => {
          const value = props.values[field.key] || "";
          return (
            <label key={field.key} className="grid gap-1">
              <span className="text-xs efhc-text-muted">
                {field.label}
              </span>
              {field.type === "textarea" ? (
                <textarea
                  className="efhc-input min-h-24"
                  placeholder={field.placeholder}
                  value={value}
                  onChange={(e) => {
                    props.onChange(field.key, e.target.value);
                  }}
                />
              ) : (
                <input
                  className="efhc-input"
                  inputMode={
                    field.type === "number"
                      ? "numeric"
                      : undefined
                  }
                  placeholder={field.placeholder}
                  value={value}
                  onChange={(e) => {
                    props.onChange(field.key, e.target.value);
                  }}
                />
              )}
            </label>
          );
        })}
        <div className="flex gap-2 pt-1">
          <Button variant="secondary" onClick={props.onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={props.busy || props.submitDisabled}
            onClick={props.onSubmit}
          >
            {props.busy ? t("admin.working") : props.submitLabel || t("common.save")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
