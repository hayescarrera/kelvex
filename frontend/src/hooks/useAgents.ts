import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const agentKeys = {
  all: ['agents'] as const,
  list: (facilityId: string) => [...agentKeys.all, 'list', facilityId] as const,
  detail: (facilityId: string, agentId: string) => [...agentKeys.all, 'detail', facilityId, agentId] as const,
  devices: (facilityId: string, agentId: string) => [...agentKeys.all, 'devices', facilityId, agentId] as const,
  config: (facilityId: string, agentId: string) => [...agentKeys.all, 'config', facilityId, agentId] as const,
}

export function useAgents(facilityId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.list(facilityId ?? ''),
    queryFn: () => api.listAgents(facilityId!),
    enabled: !!facilityId,
    refetchInterval: 30_000, // poll every 30s for connectivity updates
  })
}

export function useAgent(facilityId: string | undefined, agentId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.detail(facilityId ?? '', agentId ?? ''),
    queryFn: () => api.getAgent(facilityId!, agentId!),
    enabled: !!facilityId && !!agentId,
    refetchInterval: 15_000,
  })
}

export function useRegisterAgent(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; hardware_type?: string }) => api.registerAgent(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.list(facilityId) })
      toast.success('Agent registered — copy the agent key below')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to register agent'),
  })
}

export function useUpdateAgent(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: Record<string, unknown> }) =>
      api.updateAgent(facilityId, agentId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.list(facilityId) })
      toast.success('Agent updated')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDeleteAgent(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (agentId: string) => api.deleteAgent(facilityId, agentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.list(facilityId) })
      toast.success('Agent decommissioned')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useScanNetwork(facilityId: string) {
  return useMutation({
    mutationFn: ({ agentId, subnet }: { agentId: string; subnet?: string }) =>
      api.scanNetwork(facilityId, agentId, subnet),
    onSuccess: (data) => toast.success(data.message || 'Network scan queued'),
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDiscoveries(facilityId: string | undefined, agentId: string | undefined) {
  return useQuery({
    queryKey: [...agentKeys.all, 'discoveries', facilityId, agentId] as const,
    queryFn: () => api.getDiscoveries(facilityId!, agentId!),
    enabled: !!facilityId && !!agentId,
    refetchInterval: 10_000, // poll while waiting for scan results
  })
}

export function useApproveDiscovery(facilityId: string, agentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.approveDiscovery(facilityId, agentId, data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: agentKeys.devices(facilityId, agentId) })
      qc.invalidateQueries({ queryKey: [...agentKeys.all, 'discoveries', facilityId, agentId] })
      qc.invalidateQueries({ queryKey: ['compressor-summary', facilityId] })
      qc.invalidateQueries({ queryKey: ['compressors', facilityId] })
      toast.success(data.message || 'Device approved and compressor created')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useTestAgent(facilityId: string) {
  return useMutation({
    mutationFn: (agentId: string) => api.testAgent(facilityId, agentId),
    onSuccess: (data) => toast.success(data.message || 'Test command queued'),
    onError: (e: Error) => toast.error(e.message),
  })
}

// ── Device Profiles ─────────────────────────

export function useDeviceProfiles(manufacturer?: string) {
  return useQuery({
    queryKey: ['device-profiles', manufacturer],
    queryFn: () => api.listDeviceProfiles(manufacturer),
  })
}

// ── Agent Devices ───────────────────────────

export function useAgentDevices(facilityId: string | undefined, agentId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.devices(facilityId ?? '', agentId ?? ''),
    queryFn: () => api.listAgentDevices(facilityId!, agentId!),
    enabled: !!facilityId && !!agentId,
    refetchInterval: 30_000,
  })
}

export function useAddAgentDevice(facilityId: string, agentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.addAgentDevice(facilityId, agentId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.devices(facilityId, agentId) })
      qc.invalidateQueries({ queryKey: agentKeys.config(facilityId, agentId) })
      toast.success('Device added')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useRemoveAgentDevice(facilityId: string, agentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (deviceId: string) => api.removeAgentDevice(facilityId, agentId, deviceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.devices(facilityId, agentId) })
      qc.invalidateQueries({ queryKey: agentKeys.config(facilityId, agentId) })
      toast.success('Device removed')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useAgentConfig(facilityId: string | undefined, agentId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.config(facilityId ?? '', agentId ?? ''),
    queryFn: () => api.getAgentConfig(facilityId!, agentId!),
    enabled: !!facilityId && !!agentId,
  })
}
