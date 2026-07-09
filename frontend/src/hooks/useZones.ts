import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import type { ZoneCreate, ZoneSensorCreate } from '../lib/api'

export const zoneKeys = {
  all: ['zones'] as const,
  list: (facilityId: string) => [...zoneKeys.all, 'list', facilityId] as const,
  sensors: (facilityId: string, zoneId: string) => [...zoneKeys.all, 'sensors', facilityId, zoneId] as const,
}

export function useZones(facilityId: string) {
  return useQuery({
    queryKey: zoneKeys.list(facilityId),
    queryFn: () => api.listZones(facilityId),
    enabled: !!facilityId,
  })
}

export function useCreateZone(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ZoneCreate) => api.createZone(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: zoneKeys.list(facilityId) })
      toast.success('Zone created')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create zone'),
  })
}

export function useUpdateZone(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ zoneId, data }: { zoneId: string; data: Partial<ZoneCreate> }) =>
      api.updateZone(facilityId, zoneId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: zoneKeys.list(facilityId) })
      toast.success('Zone updated')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update zone'),
  })
}

export function useDeleteZone(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (zoneId: string) => api.deleteZone(facilityId, zoneId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: zoneKeys.list(facilityId) })
      toast.success('Zone deleted')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete zone'),
  })
}

export function useZoneSensors(facilityId: string, zoneId: string) {
  return useQuery({
    queryKey: zoneKeys.sensors(facilityId, zoneId),
    queryFn: () => api.listZoneSensors(facilityId, zoneId),
    enabled: !!facilityId && !!zoneId,
  })
}

export function useCreateZoneSensor(facilityId: string, zoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ZoneSensorCreate) => api.createZoneSensor(facilityId, zoneId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: zoneKeys.sensors(facilityId, zoneId) })
      toast.success('Sensor added')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to add sensor'),
  })
}

export function useUpdateZoneSensor(facilityId: string, zoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sensorId, data }: { sensorId: string; data: Partial<ZoneSensorCreate> }) =>
      api.updateZoneSensor(facilityId, zoneId, sensorId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: zoneKeys.sensors(facilityId, zoneId) })
      toast.success('Sensor updated')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update sensor'),
  })
}

export function useDeleteZoneSensor(facilityId: string, zoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sensorId: string) => api.deleteZoneSensor(facilityId, zoneId, sensorId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: zoneKeys.sensors(facilityId, zoneId) })
      toast.success('Sensor removed')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to remove sensor'),
  })
}
