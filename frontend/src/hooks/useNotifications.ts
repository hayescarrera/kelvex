import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import type { NotificationChannelCreate } from '../lib/api'

export const notificationKeys = {
  all: ['notifications'] as const,
  channels: () => [...notificationKeys.all, 'channels'] as const,
  logs: () => [...notificationKeys.all, 'logs'] as const,
}

export function useNotificationChannels() {
  return useQuery({
    queryKey: notificationKeys.channels(),
    queryFn: () => api.listNotificationChannels(),
  })
}

export function useCreateNotificationChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: NotificationChannelCreate) => api.createNotificationChannel(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: notificationKeys.channels() })
      toast.success('Channel created')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create channel'),
  })
}

export function useUpdateNotificationChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, data }: { channelId: string; data: Partial<NotificationChannelCreate> }) =>
      api.updateNotificationChannel(channelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: notificationKeys.channels() })
      toast.success('Channel updated')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update channel'),
  })
}

export function useDeleteNotificationChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (channelId: string) => api.deleteNotificationChannel(channelId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: notificationKeys.channels() })
      toast.success('Channel deleted')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete channel'),
  })
}

export function useTestNotificationChannel() {
  return useMutation({
    mutationFn: (channelId: string) => api.testNotificationChannel(channelId),
    onSuccess: (result) => {
      if (result.success) {
        toast.success('Test notification sent')
      } else {
        toast.error(result.error || 'Test failed')
      }
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to send test'),
  })
}

export function useNotificationLogs(limit = 50) {
  return useQuery({
    queryKey: [...notificationKeys.logs(), limit],
    queryFn: () => api.listNotificationLogs(limit),
  })
}
