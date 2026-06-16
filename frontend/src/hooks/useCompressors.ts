import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import toast from 'react-hot-toast'

export function useCompressors(facilityId: string | undefined) {
  return useQuery({
    queryKey: ['compressors', facilityId],
    queryFn: () => api.listCompressors(facilityId!),
    enabled: !!facilityId,
  })
}

export function useCompressorSummary(facilityId: string | undefined) {
  return useQuery({
    queryKey: ['compressor-summary', facilityId],
    queryFn: () => api.getCompressorSummary(facilityId!),
    enabled: !!facilityId,
    refetchInterval: 60_000, // refresh every minute for live data
  })
}

export function useCompressorReadings(facilityId: string | undefined, compressorId: string | undefined, hours = 24) {
  return useQuery({
    queryKey: ['compressor-readings', facilityId, compressorId, hours],
    queryFn: () => api.getCompressorReadings(facilityId!, compressorId!, hours),
    enabled: !!facilityId && !!compressorId,
    refetchInterval: 60_000,
  })
}

export function useCreateCompressor(facilityId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.createCompressor(facilityId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['compressors', facilityId] })
      qc.invalidateQueries({ queryKey: ['compressor-summary', facilityId] })
      toast.success('Compressor added')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useUpdateCompressor(facilityId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      api.updateCompressor(facilityId!, id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['compressors', facilityId] })
      qc.invalidateQueries({ queryKey: ['compressor-summary', facilityId] })
      toast.success('Compressor updated')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDeleteCompressor(facilityId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (compressorId: string) => api.deleteCompressor(facilityId!, compressorId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['compressors', facilityId] })
      qc.invalidateQueries({ queryKey: ['compressor-summary', facilityId] })
      toast.success('Compressor removed')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useHealthCheck(facilityId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (compressorId: string) => api.triggerHealthCheck(facilityId!, compressorId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['compressor-summary', facilityId] })
      toast.success('Health check complete')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useHealthTrend(facilityId: string | undefined, compressorId: string | undefined, days = 30) {
  return useQuery({
    queryKey: ['compressor-health-trend', facilityId, compressorId, days],
    queryFn: () => api.getHealthTrend(facilityId!, compressorId!, days),
    enabled: !!facilityId && !!compressorId,
  })
}
