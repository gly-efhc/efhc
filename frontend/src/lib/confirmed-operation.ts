let inFlight = false;

export async function runConfirmedOperation(
  isCurrent: () => boolean,
  confirm: () => Promise<boolean>,
  dispatch: (beforeSend: () => boolean) => Promise<void>,
): Promise<void> {
  if (inFlight || !isCurrent()) return;
  inFlight = true;
  try {
    if (await confirm() !== true || !isCurrent()) return;
    await dispatch(isCurrent);
  } finally {
    inFlight = false;
  }
}
