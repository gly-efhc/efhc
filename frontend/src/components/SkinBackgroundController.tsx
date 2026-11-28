import { useEffect } from "react";

import { getShopSkinBgUrl } from "../lib/skins";
import { useMySkins } from "../queries/useSkins";

export function SkinBackgroundController(props: {
  onChange: (url: string | null) => void;
}) {
  const { onChange } = props;
  const query = useMySkins();
  const activeSkinId = Number(query.data?.active_skin_id || 0);
  const refetch = query.refetch;

  useEffect(() => {
    onChange(getShopSkinBgUrl(activeSkinId));
  }, [activeSkinId, onChange]);

  useEffect(() => {
    const onChanged = () => {
      void refetch();
    };
    window.addEventListener("efhc_shop_skin_changed", onChanged);
    return () => window.removeEventListener(
      "efhc_shop_skin_changed",
      onChanged,
    );
  }, [refetch]);

  return null;
}
