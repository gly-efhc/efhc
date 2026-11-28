import { resolveInterfaceVariantStyle } from "../../lib/interfaceVariantRegistry";
import React, { useContext, useState } from "react";

import { LayoutContext } from "../../components/Layout";
import { ReferralRoster } from "../../components/referrals/ReferralRoster";
import { Button } from "../../components/ui/Button";
import { GamePageShell } from "../../components/ui/GameShell";
import { useT } from "../../hooks/useT";
import { hapticSelection } from "../../lib/telegram";
import { useReferralStats } from "../../queries/useReferrals";
import { useInterfaceCustomization } from "../../hooks/useInterfaceCustomization";
import type { ReferralTab } from "../../services/referrals.service";

export default function MyReferralsPage() {
  const t = useT();
  const ctx = useContext(LayoutContext);
  const statsQ = useReferralStats();
  const customization = useInterfaceCustomization();
  const [tab, setTab] = useState<ReferralTab>("active");
  const stats = statsQ.data;

  const selectTab = (next: ReferralTab) => {
    hapticSelection(ctx.settings.haptics_enabled);
    setTab(next);
  };

  return (
    <GamePageShell
      className="efhc-referrals-shell efhc-referrals-my-page"
      data-referrals-my-route="/referrals/my"
      data-rg={resolveInterfaceVariantStyle("RG", customization.effective.RG)}
    >
      <h1 className="efhc-subpage-centered-title">{t("referrals.my_referrals")}</h1>
      <div data-referrals-segments="active-inactive" data-referrals-list-mode="segmented-page" className="efhc-referrals-segment-surface">
        <div className="efhc-segmented efhc-referrals-tabs mb-3">
          <Button
            variant={tab === "active" ? "primary" : "secondary"}
            onClick={() => selectTab("active")}
          >
            {t("referrals.active")} ({stats?.active_referrals ?? 0})
          </Button>
          <Button
            variant={tab === "inactive" ? "primary" : "secondary"}
            onClick={() => selectTab("inactive")}
          >
            {t("referrals.inactive")} ({stats?.inactive_referrals ?? 0})
          </Button>
        </div>
        <ReferralRoster tab={tab} />
      </div>
    </GamePageShell>
  );
}
