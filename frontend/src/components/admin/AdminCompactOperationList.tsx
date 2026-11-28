import React from "react";

export type AdminCompactOperationRow = {
  id: React.Key;
  operation: React.ReactNode;
  amount?: React.ReactNode;
  subject?: React.ReactNode;
  time?: React.ReactNode;
  action?: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  ariaLabel?: string;
  tone?: "success" | "neon";
};

export function AdminCompactOperationList(props: {
  rows: AdminCompactOperationRow[];
  className?: string;
}) {
  return (
    <div
      className={`efhc-admin-compact-operation-list ${props.className || ""}`.trim()}
      data-admin-primitive="list"
      data-eam-family="EAM-ADMIN-006"
      data-admin-operation-density="bank-compact"
    >
      {props.rows.map((row) => {
        const content = (
          <>
            <strong className="efhc-admin-compact-operation_operation">
              {row.operation}
            </strong>
            <b className="efhc-admin-compact-operation_amount">
              {row.amount ?? "—"}
            </b>
            <span className="efhc-admin-compact-operation_subject">
              {row.subject ?? "—"}
            </span>
            <time className="efhc-admin-compact-operation_time">
              {row.time ?? "—"}
            </time>
            {row.action ? (
              <span className="efhc-admin-compact-operation_action">
                {row.action}
              </span>
            ) : null}
          </>
        );
        if (row.onClick) {
          return (
            <button
              key={row.id}
              type="button"
              className="efhc-admin-compact-operation-row"
              data-admin-primitive="list-row"
              data-active={row.active ? "true" : "false"}
              data-has-action={row.action ? "true" : "false"}
              data-tone={row.tone || undefined}
              aria-label={row.ariaLabel}
              onClick={row.onClick}
            >
              {content}
            </button>
          );
        }
        return (
          <div
            key={row.id}
            className="efhc-admin-compact-operation-row"
            data-admin-primitive="list-row"
            data-active={row.active ? "true" : "false"}
            data-has-action={row.action ? "true" : "false"}
            data-tone={row.tone || undefined}
          >
            {content}
          </div>
        );
      })}
    </div>
  );
}
