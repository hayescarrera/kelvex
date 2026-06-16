import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import type { SequenceCreate, AutomationRuleCreate, ScheduleCreate } from '../lib/api'

export const controlKeys = {
  all: ['controls'] as const,
  sequences: (facilityId: string) => [...controlKeys.all, 'sequences', facilityId] as const,
  rules: (facilityId: string) => [...controlKeys.all, 'rules', facilityId] as const,
  schedules: (facilityId: string) => [...controlKeys.all, 'schedules', facilityId] as const,
  commands: (facilityId: string, state?: string) => [...controlKeys.all, 'commands', facilityId, state ?? ''] as const,
  auditLog: (facilityId: string) => [...controlKeys.all, 'audit-log', facilityId] as const,
}

export function useSequences(facilityId: string | undefined) {
  return useQuery({
    queryKey: controlKeys.sequences(facilityId ?? ''),
    queryFn: () => api.listSequences(facilityId!),
    enabled: !!facilityId,
  })
}

export function useCreateSequence(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SequenceCreate) => api.createSequence(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.sequences(facilityId) })
      toast.success('Sequence created')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create sequence'),
  })
}

export function useRunSequence(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sequenceId: string) => api.runSequence(facilityId, sequenceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.sequences(facilityId) })
      toast.success('Sequence dispatched')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to run sequence'),
  })
}

export function useAutomationRules(facilityId: string | undefined) {
  return useQuery({
    queryKey: controlKeys.rules(facilityId ?? ''),
    queryFn: () => api.listAutomationRules(facilityId!),
    enabled: !!facilityId,
  })
}

export function useCreateAutomationRule(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AutomationRuleCreate) => api.createAutomationRule(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.rules(facilityId) })
      toast.success('Automation rule created')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create rule'),
  })
}

export function useUpdateAutomationRule(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ruleId, data }: { ruleId: string; data: Partial<AutomationRuleCreate> }) =>
      api.updateAutomationRule(facilityId, ruleId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.rules(facilityId) })
      toast.success('Rule updated')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update rule'),
  })
}

export function useDeleteAutomationRule(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ruleId: string) => api.deleteAutomationRule(facilityId, ruleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.rules(facilityId) })
      toast.success('Rule deleted')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete rule'),
  })
}

export function useSchedules(facilityId: string | undefined) {
  return useQuery({
    queryKey: controlKeys.schedules(facilityId ?? ''),
    queryFn: () => api.listSchedules(facilityId!),
    enabled: !!facilityId,
  })
}

export function useCreateSchedule(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ScheduleCreate) => api.createSchedule(facilityId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.schedules(facilityId) })
      toast.success('Schedule created')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create schedule'),
  })
}

export function useDeleteSchedule(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (scheduleId: string) => api.deleteSchedule(facilityId, scheduleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.schedules(facilityId) })
      toast.success('Schedule deleted')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete schedule'),
  })
}

export function usePlantCommands(facilityId: string | undefined, state?: string) {
  return useQuery({
    queryKey: controlKeys.commands(facilityId ?? '', state),
    queryFn: () => api.listPlantCommands(facilityId!, state),
    enabled: !!facilityId,
    refetchInterval: 10_000,
  })
}

export function useCancelCommand(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (commandId: string) => api.cancelPlantCommand(facilityId, commandId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.commands(facilityId) })
      toast.success('Command cancelled')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to cancel command'),
  })
}

export function useApproveCommand(facilityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (commandId: string) => api.approvePlantCommand(facilityId, commandId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: controlKeys.commands(facilityId) })
      toast.success('Command approved')
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to approve command'),
  })
}

export function useControlAuditLog(facilityId: string | undefined, limit = 50) {
  return useQuery({
    queryKey: controlKeys.auditLog(facilityId ?? ''),
    queryFn: () => api.getControlAuditLog(facilityId!, limit),
    enabled: !!facilityId,
  })
}
