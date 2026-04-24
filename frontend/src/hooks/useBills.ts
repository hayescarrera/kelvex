import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const billKeys = {
  all: ['bills'] as const,
  list: (facilityId: string) => [...billKeys.all, 'list', facilityId] as const,
  analyses: (facilityId: string) => [...billKeys.all, 'analyses', facilityId] as const,
}

export function useBills(facilityId: string) {
  return useQuery({
    queryKey: billKeys.list(facilityId),
    queryFn: () => api.listBills(facilityId),
    enabled: !!facilityId,
  })
}

export function useAnalyses(facilityId: string) {
  return useQuery({
    queryKey: billKeys.analyses(facilityId),
    queryFn: () => api.listAnalyses(facilityId),
    enabled: !!facilityId,
  })
}

export function useCreateBill(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Parameters<typeof api.createBill>[1]) => api.createBill(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: billKeys.list(facilityId) })
      toast.success('Bill added')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to add bill'),
  })
}

export function useUploadBills(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.uploadBills(facilityId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: billKeys.list(facilityId) })
      toast.success('Bills uploaded')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to upload bills'),
  })
}

export function useAnalyzeBill(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (billId: string) => api.analyzeBill(facilityId, billId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: billKeys.analyses(facilityId) })
      toast.success('Analysis complete')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to analyze bill'),
  })
}

export function useDeleteBill(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (billId: string) => api.deleteBill(facilityId, billId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: billKeys.list(facilityId) })
      toast.success('Bill deleted')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete bill'),
  })
}
