import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const equipmentKeys = {
  all: ['equipment'] as const,
  list: (facilityId: string) => [...equipmentKeys.all, 'list', facilityId] as const,
}

export function useEquipment(facilityId: string) {
  return useQuery({
    queryKey: equipmentKeys.list(facilityId),
    queryFn: () => api.listEquipment(facilityId),
    enabled: !!facilityId,
  })
}

export function useCreateEquipment(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Parameters<typeof api.createEquipment>[1]) => api.createEquipment(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: equipmentKeys.list(facilityId) })
      toast.success('Equipment added')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to add equipment'),
  })
}

export function useDeleteEquipment(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (equipmentId: string) => api.deleteEquipment(facilityId, equipmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: equipmentKeys.list(facilityId) })
      toast.success('Equipment removed')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete equipment'),
  })
}
