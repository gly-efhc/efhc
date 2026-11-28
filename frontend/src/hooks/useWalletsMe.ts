import { useProfileWallets } from "../queries/useProfile";

export function useWalletsMe() {
  return useProfileWallets();
}
