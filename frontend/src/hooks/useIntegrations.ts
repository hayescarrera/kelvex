import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const integrationKeys = {
  all: ['integrations'] as const,
  list: (facilityId: string) => [...integrationKeys.all, 'list', facilityId] as const,
  providers: () => [...integrationKeys.all, 'providers'] as const,
}

export function useIntegrations(facilityId: string) {
  return useQuery({
    queryKey: integrationKeys.list(facilityId),
    queryFn: () => api.listIntegrations(facilityId),
    enabled: !!facilityId,
  })
}

export function useProviders() {
  return useQuery({
    queryKey: integrationKeys.providers(),
    queryFn: () => api.listProviders(),
    staleTime: 5 * 60_000,
  })
}

export function useCreateIntegration(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      provider: string; integration_type: string; name: string;
      description?: string; config?: Record<string, unknown>;
      credential_id?: string; enabled?: boolean;
    }) => api.createIntegration(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: integrationKeys.list(facilityId) })
      toast.success('Integration added')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create integration'),
  })
}

export function useTestIntegration(facilityId: string) {
  return useMutation({
    mutationFn: (integrationId: string) => api.testIntegration(facilityId, integrationId),
    onSuccess: (data) => {
      if (data.success) toast.success(`Connection OK (${data.latency_ms}ms)`)
      else toast.error(data.error || 'Connection test failed')
    },
    onError: (e: Error) => toast.error(e.message || 'Connection test failed'),
  })
}

export function useDeleteIntegration(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (integrationId: string) => api.deleteIntegration(facilityId, integrationId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: integrationKeys.list(facilityId) })
      toast.success('Integration removed')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete integration'),
  })
}

export function useTriggerPoll(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (integrationId: string) => api.triggerPoll(facilityId, integrationId),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: integrationKeys.list(facilityId) })
      toast.success(`Polled ${data.readings_count} readings`)
    },
    onError: (e: Error) => toast.error(e.message || 'Poll failed'),
  })
}
