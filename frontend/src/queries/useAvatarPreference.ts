/** Owner-keyed server avatar state. No localStorage/Telegram CloudStorage authority. */
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { apiRequest } from "../lib/api";
import {
  avatarEnvelopeSchema, avatarSourcesSchema, ICON_FALLBACK, resolveAvatar,
  type AvatarEnvelope, type AvatarPreference,
} from "../lib/avatarPreference";

const avatarKey = (id: string) => ["profile", id, "avatar"] as const;
const sourcesKey = (id: string) => ["profile", id, "avatar-sources"] as const;

export function useAvatarPreference() {
  const owner = useAuthOwnerGlobalId();
  const id = owner ? String(owner) : "";
  const enabled = Boolean(id);
  const preferenceQuery = useQuery({
    queryKey: avatarKey(id), enabled,
    queryFn: async ({ signal }) => avatarEnvelopeSchema.parse(
      await apiRequest<unknown>("/profile/avatar", "GET", { signal }),
    ), staleTime: 60_000,
  });
  const sourcesQuery = useQuery({
    queryKey: sourcesKey(id), enabled,
    queryFn: async ({ signal }) => avatarSourcesSchema.parse(
      await apiRequest<unknown>("/profile/avatar/sources", "GET", { signal }),
    ), staleTime: 60_000,
  });
  const avatar = preferenceQuery.data
    ? resolveAvatar(preferenceQuery.data.preference, sourcesQuery.data?.items ?? [])
    : ICON_FALLBACK;
  const queryClient = useQueryClient();
  const currentOwner = useRef(id);
  // Render-time owner update prevents a cross-account response before effects run.
  currentOwner.current = id;
  const save = useMutation({
    mutationFn: async (next: { preference: AvatarPreference; expectedRevision: number; ownerAtStart: string }) =>
      avatarEnvelopeSchema.parse(await apiRequest<unknown>("/profile/avatar", "PUT", {
        body: { preference: next.preference, expectedRevision: next.expectedRevision },
      })),
    onSuccess: (result: AvatarEnvelope, variables) => {
      if (variables.ownerAtStart && currentOwner.current === variables.ownerAtStart) {
        queryClient.setQueryData(avatarKey(variables.ownerAtStart), result);
      }
    },
  });
  return { owner: id, preferenceQuery, sourcesQuery, avatar, save };
}
