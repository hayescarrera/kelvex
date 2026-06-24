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

export const inviteKeys = {
  all: ['invites'] as const,
  list: () => [...inviteKeys.all, 'list'] as const,
}

export function useSendInvite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { email: string; role?: string; facility_ids?: string[] }) =>
      api.sendInvite(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: inviteKeys.list() })
      toast.success('Invite sent')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to send invite'),
  })
}

export function usePendingInvites() {
  return useQuery({
    queryKey: inviteKeys.list(),
    queryFn: () => api.listInvites(),
  })
}

export function useRevokeInvite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (inviteId: string) => api.revokeInvite(inviteId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: inviteKeys.list() })
      toast.success('Invite revoked')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to revoke invite'),
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
