import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

// Hook compartido para la lista de señales. react-query deduplica las peticiones
// y comparte el caché entre páginas (Dashboard, Calendario), evitando que cada
// vista vuelva a pedir /api/signals por su cuenta. Refresca cada 30s para mantener
// los precios al día.
export function useSignals(options = {}) {
  return useQuery({
    queryKey: ["signals"],
    queryFn: api.signals,
    staleTime: 20_000,
    refetchInterval: 30_000,
    ...options,
  });
}
