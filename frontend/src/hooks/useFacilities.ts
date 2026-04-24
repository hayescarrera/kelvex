import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const facilityKeys = {
  all: ['facilities'] as const,
  list: () => [...facilityKeys.all, 'list'] as const,
  detail: (id: string) => [...facilityKeys.all, 'detail', id] as const,
}

export function useFacilities() {
  return useQuery({
    queryKey: facilityKeys.list(),
    queryFn: () => api.listFacilities(),
  })
}

export function useFacility(id: string) {
  return useQuery({
    queryKey: facilityKeys.detail(id),
    queryFn: () => api.getFacility(id),
    enabled: !!id,
  })
}

export function useCreateFacility() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Parameters<typeof api.createFacility>[0]) => api.createFacility(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: facilityKeys.list() })
      toast.success('Facility created')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create facility'),
  })
}

export function useUpdateFacility(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.updateFacility(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: facilityKeys.detail(id) })
      qc.invalidateQueries({ queryKey: facilityKeys.list() })
      toast.success('Facility updated')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update facility'),
  })
}

export function useDeleteFacility() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.request(`/facilities/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: facilityKeys.list() })
      toast.success('Facility deleted')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete facility'),
  })
}
