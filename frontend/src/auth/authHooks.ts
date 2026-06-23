import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../api/queryKeys";
import { UserModel } from "../schemas/users";
import { getCurrentUser } from "../api/auth";

export function useCurrentUser() {
  const query = useQuery<UserModel | null>({
    queryKey: queryKeys.auth.me(),
    queryFn: getCurrentUser,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  return query;
}
