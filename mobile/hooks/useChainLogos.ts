import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getChains } from "../services/api";

/**
 * Returns a map of chain_name → logo_url from the cached chains query.
 */
export function useChainLogos(): Record<string, string | null> {
  const { data: chains } = useQuery({
    queryKey: ["chains"],
    queryFn: getChains,
    staleTime: 3600000,
  });

  return useMemo(() => {
    const map: Record<string, string | null> = {};
    for (const c of chains ?? []) {
      map[c.name] = c.logo_url;
      map[c.slug] = c.logo_url;
    }
    return map;
  }, [chains]);
}
