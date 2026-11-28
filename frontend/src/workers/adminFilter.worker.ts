type UsersCriteria = {
  segment: "active" | "all" | "inactive" | "vip" | "wallets";
};

type LogsCriteria = {
  now: number;
  severity: string;
  source: string;
  time: "day" | "hour" | "latest";
};

type WorkerRequest = {
  criteria: LogsCriteria | UsersCriteria;
  id: number;
  items: Array<Record<string, unknown>>;
  kind: "logs" | "users";
};

function usersMatch(
  item: Record<string, unknown>,
  criteria: UsersCriteria,
): boolean {
  if (criteria.segment === "active") return Boolean(item.is_active);
  if (criteria.segment === "inactive") return !Boolean(item.is_active);
  if (criteria.segment === "vip") return Boolean(item.is_vip);
  if (criteria.segment === "wallets") return Boolean(item.ton_wallet);
  return true;
}

function logsMatch(
  item: Record<string, unknown>,
  criteria: LogsCriteria,
): boolean {
  if (
    criteria.source !== "all" &&
    String(item.source || "") !== criteria.source
  ) {
    return false;
  }
  if (
    criteria.severity !== "all" &&
    String(item.severity || "") !== criteria.severity
  ) {
    return false;
  }
  if (criteria.time === "latest") return true;
  const timestamp = Date.parse(String(item.createdAt || ""));
  if (!Number.isFinite(timestamp)) return true;
  const age = criteria.now - timestamp;
  const limit = criteria.time === "hour"
    ? 60 * 60 * 1000
    : 24 * 60 * 60 * 1000;
  return age <= limit;
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  const indices: number[] = [];
  request.items.forEach((item, index) => {
    const match = request.kind === "users"
      ? usersMatch(item, request.criteria as UsersCriteria)
      : logsMatch(item, request.criteria as LogsCriteria);
    if (match) indices.push(index);
  });
  self.postMessage({ id: request.id, indices });
};
