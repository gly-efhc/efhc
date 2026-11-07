import React, { useMemo } from "react";
import { useRouter } from "next/router";

import { useT } from "../../hooks/useT";
import { hapticMedium, hapticSoft, openTelegramLink } from "../../lib/telegram";
import { useShopLauncher } from "../../queries/useShopLauncher";
import { usePublicHubLinks } from "../../queries/useHub";
import type { HubPublicLink } from "../../services/hub.service";
import { GamePageShell } from "../../components/ui/GameShell";

function isShopLink(link: HubPublicLink): boolean {
  return link.code === "efhc_buy";
}

function isVipLink(link: HubPublicLink): boolean {
  return link.code === "vip_getgems";
}

export default function HubPage() {
  const t = useT();
  const router = useRouter();
  const shopLauncher = useShopLauncher();
  const publicLinks = usePublicHubLinks();

  // OWNER Cycle0559: four fixed identities/positions, editable URL and visibility.
  // An empty successful response must remain empty (all slots may be disabled).

  const links = useMemo<HubPublicLink[]>(() => {
    // Fail closed: never reveal disabled links when the API is unavailable.
    const rows = publicLinks.data ?? [];
    const fixed = ["efhc_buy", "vip_getgems", "efhc_ceo", "efhc_admin"];
    return [...rows].filter((link) => link.is_active).sort((a, b) => {
      const ai = fixed.indexOf(a.code), bi = fixed.indexOf(b.code);
      if (ai >= 0 && bi >= 0) return ai - bi;
      if (ai >= 0) return -1;
      if (bi >= 0) return 1;
      return a.sort_order - b.sort_order;
    });
  }, [publicLinks.data]);

  async function openHubLink(link: HubPublicLink) {
    hapticMedium(true);
    if (isShopLink(link) && link.url === "/hub/efhc-handoff") {
      try {
        await shopLauncher.mutateAsync();
      } catch {
        hapticSoft(true);
      }
      return;
    }
    if (link.url.startsWith("/")) {
      await router.push(link.url);
      return;
    }
    openTelegramLink(link.url);
  }

  return (
    <GamePageShell
      className="efhc-hub-page efhc-hub-actions"
      data-hu="HU-01"
      data-public-surface="hub"
      data-hub-runtime="dynamic-active-links"
      data-hub-visible-action-count={links.length}
      data-hub-empty-slots="none"
      data-hub-commerce-copy="forbidden-before-exit"
    >
      <section
        className="efhc-hub-choice-grid"
        data-hub-link-slot-grid="two-per-row-active-only"
        aria-label="Hub"
        data-i18n-fixed-token="Hub"
      >
        {links.map((link) => {
          const shop = isShopLink(link);
          const vip = isVipLink(link);
          return (
            <button
              key={String(link.id)}
              type="button"
              className="efhc-hub-choice"
              data-hub-link-id={String(link.id)}
              data-hub-link-code={link.code}
              data-hub-link-url={link.url}
              data-hub-link-active="true"
              disabled={shop && shopLauncher.isPending}
              aria-busy={shop && shopLauncher.isPending}
              onClick={() => {
                if (!(shop && shopLauncher.isPending)) void openHubLink(link);
              }}
            >
              <strong>{shop && shopLauncher.isPending ? t("common.loading") :
                shop ? t("hub.action_shop") : vip ? "EFHC VIP NFT" :
                link.code === "efhc_ceo" ? t("hub.action_ceo") :
                link.code === "efhc_admin" ? t("hub.action_admin") : link.title}</strong>
            </button>
          );
        })}
      </section>
    </GamePageShell>
  );
}
