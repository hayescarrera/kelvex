import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export const memberKeys = {
  all: ['members'] as const,
  list: () => [...memberKeys.all, 'list'] as const,
}

export function useOrgMembers() {
  return useQuery({
    queryKey: memberKeys.list(),
    queryFn: () => api.listOrgMembers(),
  })
}

export function useInviteMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { email: string; full_name: string; role?: string; password: string; facility_ids?: string[] }) =>
      api.inviteMember(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: memberKeys.list() })
      toast.success('Member invited')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to invite member'),
  })
}

export function useUpdateMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: { role?: string; is_active?: boolean; full_name?: string; facility_ids?: string[] } }) =>
      api.updateMember(userId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: memberKeys.list() })
      toast.success('Member updated')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update member'),
  })
}

export function useRemoveMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => api.removeMember(userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: memberKeys.list() })
      toast.success('Member removed')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to remove member'),
  })
}
