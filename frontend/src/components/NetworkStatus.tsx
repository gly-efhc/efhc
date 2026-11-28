import React, { useEffect, useState } from "react";

export function NetworkStatus({ t }: { t: (key: string) => string }) {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const sync = () => setOnline(navigator.onLine);
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);
  if (online) return null;
  return (
    <div className="efhc-network-status" role="status" aria-live="polite">
      {t("common.offline")}
    </div>
  );
}
