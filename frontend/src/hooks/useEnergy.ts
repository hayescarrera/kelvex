import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import type { EnergyOpportunity } from '../lib/api'

export function useRateWindows(facilityId: string | undefined, targetDate?: string) {
  return useQuery({
    queryKey: ['rate-windows', facilityId, targetDate],
    queryFn: () => api.getRateWindows(facilityId!, targetDate),
    enabled: !!facilityId,
  })
}

export function useCurrentRate(facilityId: string | undefined) {
  return useQuery({
    queryKey: ['current-rate', facilityId],
    queryFn: () => api.getCurrentRate(facilityId!),
    enabled: !!facilityId,
    refetchInterval: 300_000, // every 5 min
  })
}

export function usePrecoolSchedule(facilityId: string | undefined, targetDate?: string) {
  return useQuery({
    queryKey: ['precool-schedule', facilityId, targetDate],
    queryFn: () => api.getPrecoolSchedule(facilityId!, targetDate),
    enabled: !!facilityId,
  })
}

export function useDemandForecast(facilityId: string | undefined) {
  return useQuery({
    queryKey: ['demand-forecast', facilityId],
    queryFn: () => api.getDemandForecast(facilityId!),
    enabled: !!facilityId,
    refetchInterval: 300_000,
  })
}

export function useSavingsProjection(facilityId: string | undefined) {
  return useQuery({
    queryKey: ['savings-projection', facilityId],
    queryFn: () => api.getSavingsProjection(facilityId!),
    enabled: !!facilityId,
  })
}

export function useOpportunitiesSummary(facilityId: string | undefined) {
  return useQuery({
    queryKey: ['opp-summary', facilityId],
    queryFn: () => api.getOpportunitiesSummary(facilityId!),
    enabled: !!facilityId,
    refetchInterval: 300_000,
  })
}

export function useOpportunities(facilityId: string | undefined, status = 'open') {
  return useQuery({
    queryKey: ['opportunities', facilityId, status],
    queryFn: () => api.getOpportunities(facilityId!, { status, limit: 100 }),
    enabled: !!facilityId,
    refetchInterval: 300_000,
  })
}

export function usePatchOpportunity(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ oppId, status }: { oppId: string; status: string }) =>
      api.patchOpportunity(facilityId, oppId, { status }),
    onSuccess: (_data: EnergyOpportunity) => {
      qc.invalidateQueries({ queryKey: ['opportunities', facilityId] })
      qc.invalidateQueries({ queryKey: ['opp-summary', facilityId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

// ── Rate Schedule Management ─────────────────
export function useUtilities() {
  return useQuery({
    queryKey: ['utilities'],
    queryFn: () => api.listUtilities(),
  })
}

export function useRateSchedules(utilityId?: string) {
  return useQuery({
    queryKey: ['rate-schedules', utilityId],
    queryFn: () => api.listRateSchedules(utilityId),
  })
}

export function useCreateUtility() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; state?: string; iso_region?: string }) => api.createUtility(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['utilities'] })
      toast.success('Utility created')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useCreateRateSchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.createRateSchedule(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rate-schedules'] })
      toast.success('Rate schedule created')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useAssignRateSchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ facilityId, scheduleId }: { facilityId: string; scheduleId: string }) =>
      api.assignRateSchedule(facilityId, scheduleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['facilities'] })
      toast.success('Rate schedule assigned')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}
