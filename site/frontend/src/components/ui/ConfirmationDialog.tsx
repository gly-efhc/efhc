import type { ColorThemeId } from "../../lib/colorThemeRegistry";
import { Modal } from "./Modal";

type ConfirmationRequest = {
  title: string;
  detail?: string;
  actionLabel: string;
};

export function ConfirmationDialog(props: {
  request: ConfirmationRequest | null;
  colorThemeId: ColorThemeId;
  cancelLabel: string;
  onDecision: (approved: boolean) => void;
}) {
  return (
    <Modal
      open={props.request !== null}
      title={props.request?.title ?? ""}
      portalColorThemeId={props.colorThemeId}
      surface="confirmation"
      onClose={() => props.onDecision(false)}
    >
      {props.request?.detail ? <p>{props.request.detail}</p> : null}
      <div className="efhc-confirmation-actions">
        <button type="button" data-modal-initial-focus onClick={() => props.onDecision(false)}>{props.cancelLabel}</button>
        <button type="button" onClick={() => props.onDecision(true)}>{props.request?.actionLabel}</button>
      </div>
    </Modal>
  );
}
