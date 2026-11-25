import type { ComponentProps } from "react";
import { Button } from "../../ui/Button";
import { TelegramStatusBadge } from "../../ui/telegram/TelegramStatusBadge";
import styles from "../wallet-cards.module.css";

type Props = Pick<ComponentProps<"button">, "children" | "disabled" | "onClick"> & {
  sizeLabel: string;
};

export function WalletCardAction({ sizeLabel, children, ...props }: Props) {
  return (
    <span className={styles.actionBox}>
      <span className={styles.actionMeasure} aria-hidden="true">
        <TelegramStatusBadge label={sizeLabel} tone="primary" />
      </span>
      <Button {...props} variant="secondary" className={styles.actionButton}>
        <span>{children}</span>
      </Button>
    </span>
  );
}
