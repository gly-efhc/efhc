export function isAdminVisualProofMode(): boolean {
  return process.env.NEXT_PUBLIC_EFHC_ADMIN_VISUAL_PROOF === "1";
}
