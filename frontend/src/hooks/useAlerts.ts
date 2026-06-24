import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const alertKeys = {
  all: ['alerts'] as const,
  list: (facilityId: string) => [...alertKeys.all, 'list', facilityId] as const,
  orgList: (params?: object) => [...alertKeys.all, 'org-list', params] as const,
  summary: () => [...alertKeys.all, 'summary'] as const,
}

export function useAlerts(facilityId: string | undefined, params?: { state?: string; severity?: string }) {
  return useQuery({
    queryKey: [...alertKeys.list(facilityId ?? ''), params],
    queryFn: () => api.listAlerts(facilityId!, params),
    enabled: !!facilityId,
    refetchInterval: 30_000,
  })
}

export function useAllAlerts(params?: { state?: string; severity?: string }) {
  return useQuery({
    queryKey: alertKeys.orgList(params),
    queryFn: () => api.listAllAlerts(params),
    refetchInterval: 30_000,
  })
}

export function useAlertSummary() {
  return useQuery({
    queryKey: alertKeys.summary(),
    queryFn: () => api.getAlertSummary(),
    refetchInterval: 30_000,
  })
}

export function useUpdateAlert(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ alertId, data }: { alertId: string; data: { state?: string; resolution_note?: string } }) =>
      api.updateAlert(facilityId, alertId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: alertKeys.list(facilityId) })
      qc.invalidateQueries({ queryKey: alertKeys.summary() })
      const action = variables.data.state === 'resolved' ? 'resolved' : 'updated'
      toast.success(`Alert ${action}`)
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update alert'),
  })
}
