const API_BASE = '/api/v1'

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

class ApiClient {
  private token: string | null = null
  private refreshToken: string | null = null
  private onUnauthorized: (() => void) | null = null
  private refreshPromise: Promise<string | null> | null = null

  setToken(token: string | null) {
    this.token = token
  }

  setRefreshToken(token: string | null) {
    this.refreshToken = token
  }

  setTokens(accessToken: string | null, refreshToken: string | null) {
    this.token = accessToken
    this.refreshToken = refreshToken
  }

  setUnauthorizedHandler(handler: (() => void) | null) {
    this.onUnauthorized = handler
  }

  getToken(): string | null {
    return this.token
  }

  getRefreshToken(): string | null {
    return this.refreshToken
  }

  private async refreshAccessToken(): Promise<string | null> {
    if (!this.refreshToken) return null
    if (this.refreshPromise) return this.refreshPromise

    this.refreshPromise = (async () => {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      })

      if (!response.ok) {
        this.setTokens(null, null)
        return null
      }

      const data = await response.json() as { access_token: string; refresh_token: string }
      this.setTokens(data.access_token, data.refresh_token)
      return data.access_token
    })()

    try {
      return await this.refreshPromise
    } finally {
      this.refreshPromise = null
    }
  }

  async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    return this.requestWithRetry<T>(endpoint, options, true)
  }

  private async requestWithRetry<T>(
    endpoint: string,
    options: RequestOptions,
    allowRefresh: boolean,
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: options.method || 'GET',
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    })

    if (response.status === 401) {
      if (allowRefresh) {
        const newAccessToken = await this.refreshAccessToken()
        if (newAccessToken) {
          return this.requestWithRetry<T>(endpoint, options, false)
        }
      }
      this.setTokens(null, null)
      this.onUnauthorized?.()
      throw new Error('Unauthorized')
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    if (response.status === 204) return undefined as T
    return response.json()
  }

  // ── Auth ──────────────────────────────────
  async register(email: string, password: string, fullName: string, orgName: string) {
    return this.request<{ access_token: string; refresh_token: string }>('/auth/register', {
      method: 'POST',
      body: { email, password, full_name: fullName, org_name: orgName },
    })
  }

  async login(email: string, password: string) {
    return this.request<{ access_token: string; refresh_token: string }>('/auth/login', {
      method: 'POST',
      body: { email, password },
    })
  }

  async getMe() {
    return this.request<{
      id: string; email: string; full_name: string; org_id: string; is_admin: boolean; role: string
    }>('/auth/me')
  }

  async getMyPermissions() {
    return this.request<{ role: string; permissions: string[]; has_global_access: boolean }>('/auth/me/permissions')
  }

  async updateProfile(data: { full_name?: string }) {
    return this.request<{ id: string; email: string; full_name: string; org_id: string }>(
      '/auth/me', { method: 'PATCH', body: data }
    )
  }

  // ── Facilities ────────────────────────────
  async listFacilities() {
    return this.request<{ facilities: Facility[]; total: number }>('/facilities')
  }

  async getFacility(id: string) {
    return this.request<Facility>(`/facilities/${id}`)
  }

  async createFacility(data: {
    name: string; address?: string; city?: string; state?: string;
    sqft?: number; zone_types?: string[]
  }) {
    return this.request('/facilities', { method: 'POST', body: data })
  }

  async updateFacility(id: string, data: Record<string, unknown>) {
    return this.request(`/facilities/${id}`, { method: 'PATCH', body: data })
  }

  async getFloorPlan(facilityId: string) {
    return this.request<{ facility_id: string; floor_plan: FloorPlanData }>(
      `/facilities/${facilityId}/floor-plan`
    )
  }

  async saveFloorPlan(facilityId: string, floorPlan: FloorPlanData) {
    return this.request<{ facility_id: string; floor_plan: FloorPlanData }>(
      `/facilities/${facilityId}/floor-plan`, { method: 'PUT', body: { floor_plan: floorPlan } }
    )
  }

  // ── Bills ─────────────────────────────────
  async listBills(facilityId: string) {
    return this.request<{ bills: Bill[]; total: number }>(`/facilities/${facilityId}/bills`)
  }

  async createBill(facilityId: string, data: {
    period_start: string; period_end: string;
    total_kwh?: number; total_cost?: number;
    peak_demand_kw?: number; demand_charge?: number;
    energy_charge?: number;
  }) {
    return this.request<Bill>(`/facilities/${facilityId}/bills`, { method: 'POST', body: data })
  }

  async uploadBills(facilityId: string, file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const upload = async (): Promise<Response> => {
      const headers: Record<string, string> = {}
      if (this.token) headers['Authorization'] = `Bearer ${this.token}`
      return fetch(`${API_BASE}/facilities/${facilityId}/bills/upload`, {
        method: 'POST', headers, body: formData,
      })
    }
    let response = await upload()
    if (response.status === 401) {
      const newAccessToken = await this.refreshAccessToken()
      if (newAccessToken) {
        response = await upload()
      } else {
        this.onUnauthorized?.()
      }
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }
    return response.json() as Promise<{ bills: Bill[]; total: number }>
  }

  async deleteBill(facilityId: string, billId: string) {
    return this.request(`/facilities/${facilityId}/bills/${billId}`, { method: 'DELETE' })
  }

  async analyzeBill(facilityId: string, billId: string) {
    return this.request<DemandAnalysis>(`/facilities/${facilityId}/bills/${billId}/analyze`, {
      method: 'POST',
    })
  }

  async listAnalyses(facilityId: string) {
    return this.request<{ analyses: DemandAnalysis[]; total: number }>(
      `/facilities/${facilityId}/bills/analyses`
    )
  }

  // ── Equipment ─────────────────────────────
  async listEquipment(facilityId: string) {
    return this.request<{ equipment: Equipment[]; total: number }>(
      `/facilities/${facilityId}/equipment`
    )
  }

  async createEquipment(facilityId: string, data: {
    name: string; equipment_type: string;
    manufacturer?: string; model?: string;
    controller_type?: string; protocol?: string;
  }) {
    return this.request<Equipment>(`/facilities/${facilityId}/equipment`, {
      method: 'POST', body: data,
    })
  }

  async deleteEquipment(facilityId: string, equipmentId: string) {
    return this.request(`/facilities/${facilityId}/equipment/${equipmentId}`, { method: 'DELETE' })
  }

  // ── Zones ─────────────────────────────────
  async listZones(facilityId: string) {
    return this.request<{ zones: Zone[]; total: number }>(`/facilities/${facilityId}/zones`)
  }

  async createZone(facilityId: string, data: ZoneCreate) {
    return this.request<Zone>(`/facilities/${facilityId}/zones`, { method: 'POST', body: data })
  }

  async updateZone(facilityId: string, zoneId: string, data: Partial<ZoneCreate>) {
    return this.request<Zone>(`/facilities/${facilityId}/zones/${zoneId}`, { method: 'PATCH', body: data })
  }

  async deleteZone(facilityId: string, zoneId: string) {
    return this.request(`/facilities/${facilityId}/zones/${zoneId}`, { method: 'DELETE' })
  }

  async assignEquipmentToZone(facilityId: string, zoneId: string, equipmentId: string, role?: string) {
    return this.request(`/facilities/${facilityId}/zones/${zoneId}/equipment`, {
      method: 'POST', body: { equipment_id: equipmentId, role },
    })
  }

  // ── Alerts ────────────────────────────────
  async listAlerts(facilityId: string, params?: { state?: string; severity?: string; limit?: number }) {
    const query = new URLSearchParams()
    if (params?.state) query.set('state', params.state)
    if (params?.severity) query.set('severity', params.severity)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return this.request<{ alerts: Alert[]; total: number }>(
      `/facilities/${facilityId}/alerts${qs ? '?' + qs : ''}`
    )
  }

  async listAllAlerts(params?: { state?: string; severity?: string; facility_id?: string; limit?: number }) {
    const query = new URLSearchParams()
    if (params?.state) query.set('state', params.state)
    if (params?.severity) query.set('severity', params.severity)
    if (params?.facility_id) query.set('facility_id', params.facility_id)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return this.request<{ alerts: (Alert & { facility_name: string })[]; total: number }>(
      `/alerts${qs ? '?' + qs : ''}`
    )
  }

  async updateAlert(facilityId: string, alertId: string, data: { state?: string; resolution_note?: string }) {
    return this.request<Alert>(`/facilities/${facilityId}/alerts/${alertId}`, { method: 'PATCH', body: data })
  }

  async getAlertSummary() {
    return this.request<{
      total_active: number
      by_severity: { critical: number; high: number; medium: number; low: number; info: number }
    }>('/alerts/summary')
  }

  // ── Events ────────────────────────────────
  async listEvents(facilityId: string, params?: { event_type?: string; limit?: number }) {
    const query = new URLSearchParams()
    if (params?.event_type) query.set('event_type', params.event_type)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return this.request<{ events: EventRecord[]; total: number }>(
      `/facilities/${facilityId}/events${qs ? '?' + qs : ''}`
    )
  }

  // ── Controls ──────────────────────────────
  async listSequences(facilityId: string) {
    return this.request<{ sequences: ControlSequence[]; total: number }>(
      `/facilities/${facilityId}/controls/sequences`
    )
  }

  async createSequence(facilityId: string, data: SequenceCreate) {
    return this.request<ControlSequence>(`/facilities/${facilityId}/controls/sequences`, {
      method: 'POST', body: data,
    })
  }

  async runSequence(facilityId: string, sequenceId: string) {
    return this.request<ControlSequence>(
      `/facilities/${facilityId}/controls/sequences/${sequenceId}/run`,
      { method: 'POST' }
    )
  }

  async listAutomationRules(facilityId: string) {
    return this.request<{ rules: AutomationRule[]; total: number }>(
      `/facilities/${facilityId}/controls/rules`
    )
  }

  async createAutomationRule(facilityId: string, data: AutomationRuleCreate) {
    return this.request<AutomationRule>(`/facilities/${facilityId}/controls/rules`, {
      method: 'POST', body: data,
    })
  }

  async updateAutomationRule(facilityId: string, ruleId: string, data: Partial<AutomationRuleCreate>) {
    return this.request<AutomationRule>(`/facilities/${facilityId}/controls/rules/${ruleId}`, {
      method: 'PATCH', body: data,
    })
  }

  async deleteAutomationRule(facilityId: string, ruleId: string) {
    return this.request(`/facilities/${facilityId}/controls/rules/${ruleId}`, { method: 'DELETE' })
  }

  async listSchedules(facilityId: string) {
    return this.request<{ schedules: ScheduleRecord[]; total: number }>(
      `/facilities/${facilityId}/controls/schedules`
    )
  }

  async createSchedule(facilityId: string, data: ScheduleCreate) {
    return this.request<ScheduleRecord>(
      `/facilities/${facilityId}/controls/schedules`, { method: 'POST', body: data }
    )
  }

  async deleteSchedule(facilityId: string, scheduleId: string) {
    return this.request(
      `/facilities/${facilityId}/controls/schedules/${scheduleId}`, { method: 'DELETE' }
    )
  }

  async listCommands(facilityId: string, state?: string) {
    const qs = state ? `?state=${state}` : ''
    return this.request<{ commands: Command[]; total: number }>(
      `/facilities/${facilityId}/controls/commands${qs}`
    )
  }

  // ── Edge Agents ───────────────────────────
  async listAgents(facilityId: string) {
    return this.request<{ agents: EdgeAgent[]; total: number }>(`/facilities/${facilityId}/agents`)
  }

  async registerAgent(facilityId: string, data: { name: string; hardware_type?: string }) {
    return this.request<EdgeAgent>(`/facilities/${facilityId}/agents`, { method: 'POST', body: data })
  }

  async getAgent(facilityId: string, agentId: string) {
    return this.request<EdgeAgent>(`/facilities/${facilityId}/agents/${agentId}`)
  }

  async updateAgent(facilityId: string, agentId: string, data: Record<string, unknown>) {
    return this.request<EdgeAgent>(`/facilities/${facilityId}/agents/${agentId}`, { method: 'PATCH', body: data })
  }

  async deleteAgent(facilityId: string, agentId: string) {
    return this.request(`/facilities/${facilityId}/agents/${agentId}`, { method: 'DELETE' })
  }

  async testAgent(facilityId: string, agentId: string) {
    return this.request<{ status: string; command_id: string; message: string }>(
      `/facilities/${facilityId}/agents/${agentId}/test`, { method: 'POST' }
    )
  }

  async scanNetwork(facilityId: string, agentId: string, subnet?: string) {
    return this.request<{ status: string; command_id: string; message: string }>(
      `/facilities/${facilityId}/agents/${agentId}/scan`,
      { method: 'POST', body: subnet ? { subnet } : {} }
    )
  }

  async getDiscoveries(facilityId: string, agentId: string) {
    return this.request<DiscoveryResult>(
      `/facilities/${facilityId}/agents/${agentId}/discoveries`
    )
  }

  async approveDiscovery(facilityId: string, agentId: string, data: Record<string, unknown>) {
    return this.request<{ status: string; compressor_id: string; device_id: string; message: string }>(
      `/facilities/${facilityId}/agents/${agentId}/approve-discovery`,
      { method: 'POST', body: data }
    )
  }

  // ── Device Profiles ─────────────────────────
  async listDeviceProfiles(manufacturer?: string, equipmentType?: string) {
    const params = new URLSearchParams()
    if (manufacturer) params.set('manufacturer', manufacturer)
    if (equipmentType) params.set('equipment_type', equipmentType)
    const qs = params.toString() ? `?${params}` : ''
    return this.request<{ profiles: DeviceProfile[]; total: number }>(`/device-profiles${qs}`)
  }

  async getDeviceProfile(profileId: string) {
    return this.request<DeviceProfile>(`/device-profiles/${profileId}`)
  }

  // ── Agent Devices ───────────────────────────
  async listAgentDevices(facilityId: string, agentId: string) {
    return this.request<{ devices: AgentDevice[]; total: number }>(
      `/facilities/${facilityId}/agents/${agentId}/devices`
    )
  }

  async addAgentDevice(facilityId: string, agentId: string, data: Record<string, unknown>) {
    return this.request<AgentDevice>(
      `/facilities/${facilityId}/agents/${agentId}/devices`, { method: 'POST', body: data }
    )
  }

  async updateAgentDevice(facilityId: string, agentId: string, deviceId: string, data: Record<string, unknown>) {
    return this.request<AgentDevice>(
      `/facilities/${facilityId}/agents/${agentId}/devices/${deviceId}`, { method: 'PATCH', body: data }
    )
  }

  async removeAgentDevice(facilityId: string, agentId: string, deviceId: string) {
    return this.request(
      `/facilities/${facilityId}/agents/${agentId}/devices/${deviceId}`, { method: 'DELETE' }
    )
  }

  async getAgentConfig(facilityId: string, agentId: string) {
    return this.request<AgentConfigBundle>(
      `/facilities/${facilityId}/agents/${agentId}/config`
    )
  }

  // ── Savings ───────────────────────────────
  async simulateSavings(facilityId: string) {
    return this.request<SavingsResult>(`/facilities/${facilityId}/savings/simulate`)
  }

  async getSavingsReport(facilityId: string) {
    return this.request<SavingsReport>(`/facilities/${facilityId}/savings/report`)
  }

  // ── Integrations ────────────────────────────
  async listProviders() {
    return this.request<{ providers: IntegrationProvider[] }>('/integrations/providers')
  }

  async listIntegrations(facilityId: string) {
    return this.request<{ integrations: IntegrationRecord[]; total: number }>(
      `/facilities/${facilityId}/integrations`
    )
  }

  async createIntegration(facilityId: string, data: {
    provider: string; integration_type: string; name: string;
    description?: string; config?: Record<string, unknown>;
    credential_id?: string; enabled?: boolean;
  }) {
    return this.request<IntegrationRecord>(
      `/facilities/${facilityId}/integrations`, { method: 'POST', body: data }
    )
  }

  async getIntegration(facilityId: string, integrationId: string) {
    return this.request<IntegrationRecord>(
      `/facilities/${facilityId}/integrations/${integrationId}`
    )
  }

  async updateIntegration(facilityId: string, integrationId: string, data: Record<string, unknown>) {
    return this.request<IntegrationRecord>(
      `/facilities/${facilityId}/integrations/${integrationId}`,
      { method: 'PATCH', body: data }
    )
  }

  async deleteIntegration(facilityId: string, integrationId: string) {
    return this.request<void>(
      `/facilities/${facilityId}/integrations/${integrationId}`,
      { method: 'DELETE' }
    )
  }

  async testIntegration(facilityId: string, integrationId: string) {
    return this.request<{ success: boolean; latency_ms?: number; error?: string }>(
      `/facilities/${facilityId}/integrations/${integrationId}/test`,
      { method: 'POST' }
    )
  }

  async discoverDevices(facilityId: string, integrationId: string) {
    return this.request<{ devices: IntegrationDiscoveredDevice[]; total: number }>(
      `/facilities/${facilityId}/integrations/${integrationId}/discover`,
      { method: 'POST' }
    )
  }

  async updateDeviceMap(facilityId: string, integrationId: string, mappings: Array<{
    external_id: string; equipment_id: string; metrics: Record<string, unknown>;
  }>) {
    return this.request<IntegrationRecord>(
      `/facilities/${facilityId}/integrations/${integrationId}/device-map`,
      { method: 'PUT', body: { mappings } }
    )
  }

  async triggerPoll(facilityId: string, integrationId: string) {
    return this.request<{ success: boolean; readings_count: number; error?: string }>(
      `/facilities/${facilityId}/integrations/${integrationId}/poll`,
      { method: 'POST' }
    )
  }

  // ── Credentials ─────────────────────────────
  async listCredentials(facilityId: string) {
    return this.request<{ credentials: IntegrationCredentialRecord[]; total: number }>(
      `/facilities/${facilityId}/credentials`
    )
  }

  async createCredential(facilityId: string, data: {
    provider: string; auth_type: string; credentials: Record<string, unknown>;
  }) {
    return this.request<IntegrationCredentialRecord>(
      `/facilities/${facilityId}/credentials`, { method: 'POST', body: data }
    )
  }

  async deleteCredential(facilityId: string, credentialId: string) {
    return this.request<void>(
      `/facilities/${facilityId}/credentials/${credentialId}`,
      { method: 'DELETE' }
    )
  }

  // ── Register Maps ──────────────────────────
  async listRegisterMaps(protocol?: string, manufacturer?: string) {
    const params = new URLSearchParams()
    if (protocol) params.set('protocol', protocol)
    if (manufacturer) params.set('manufacturer', manufacturer)
    const qs = params.toString()
    return this.request<{ register_maps: RegisterMapRecord[]; total: number }>(
      `/register-maps${qs ? '?' + qs : ''}`
    )
  }

  async getRegisterMap(mapId: string) {
    return this.request<RegisterMapRecord>(`/register-maps/${mapId}`)
  }

  // ── Notifications ─────────────────────────────
  async listNotificationChannels() {
    return this.request<{ channels: NotificationChannelRecord[]; total: number }>('/notifications/channels')
  }

  async createNotificationChannel(data: NotificationChannelCreate) {
    return this.request<NotificationChannelRecord>('/notifications/channels', { method: 'POST', body: data })
  }

  async updateNotificationChannel(channelId: string, data: Partial<NotificationChannelCreate>) {
    return this.request<NotificationChannelRecord>(`/notifications/channels/${channelId}`, { method: 'PATCH', body: data })
  }

  async deleteNotificationChannel(channelId: string) {
    return this.request(`/notifications/channels/${channelId}`, { method: 'DELETE' })
  }

  async testNotificationChannel(channelId: string) {
    return this.request<{ success: boolean; error?: string }>(`/notifications/channels/${channelId}/test`, { method: 'POST' })
  }

  async listNotificationLogs(limit = 50) {
    return this.request<{ logs: NotificationLogRecord[]; total: number }>(`/notifications/logs?limit=${limit}`)
  }

  // ── Notification Policies ─────────────────────
  async listNotificationPolicies(mineOnly = true) {
    return this.request<{ policies: NotificationPolicy[]; total: number }>(`/notifications/policies?mine_only=${mineOnly}`)
  }

  async createNotificationPolicy(data: NotificationPolicyCreate) {
    return this.request<NotificationPolicy>('/notifications/policies', { method: 'POST', body: data })
  }

  async updateNotificationPolicy(id: string, data: Partial<NotificationPolicyCreate>) {
    return this.request<NotificationPolicy>(`/notifications/policies/${id}`, { method: 'PATCH', body: data })
  }

  async deleteNotificationPolicy(id: string) {
    return this.request(`/notifications/policies/${id}`, { method: 'DELETE' })
  }

  async testNotificationPolicy(id: string) {
    return this.request<{ status: string }>(`/notifications/policies/${id}/test`, { method: 'POST' })
  }

  // ── Reports ───────────────────────────────────
  async getPowerReport(facilityId: string, params?: { start?: string; end?: string; interval?: string }) {
    const query = new URLSearchParams()
    if (params?.start) query.set('start', params.start)
    if (params?.end) query.set('end', params.end)
    if (params?.interval) query.set('interval', params.interval)
    const qs = query.toString()
    return this.request<PowerReport>(`/facilities/${facilityId}/reports/power${qs ? `?${qs}` : ''}`)
  }

  async getPowerSummary(facilityId: string, days = 30) {
    return this.request<PowerSummary>(`/facilities/${facilityId}/reports/power-summary?days=${days}`)
  }

  async getAuditLog(facilityId: string, params?: { start?: string; end?: string; action_type?: string; state?: string; limit?: number; offset?: number }) {
    const query = new URLSearchParams()
    if (params?.start) query.set('start', params.start)
    if (params?.end) query.set('end', params.end)
    if (params?.action_type) query.set('action_type', params.action_type)
    if (params?.state) query.set('state', params.state)
    if (params?.limit) query.set('limit', String(params.limit))
    if (params?.offset) query.set('offset', String(params.offset))
    const qs = query.toString()
    return this.request<AuditLogReport>(`/facilities/${facilityId}/reports/audit-log${qs ? `?${qs}` : ''}`)
  }

  async getDigestPreview(hours = 24) {
    return this.request<DigestPreview>(`/reports/digest-preview?hours=${hours}`)
  }

  // ── Users ─────────────────────────────────────
  async listOrgMembers() {
    return this.request<{ members: OrgMember[]; total: number }>('/auth/members')
  }

  async inviteMember(data: { email: string; full_name: string; role?: string; password: string; facility_ids?: string[] }) {
    return this.request<OrgMember>('/auth/invite', { method: 'POST', body: data })
  }

  // ── Email invite tokens ────────────────────────
  async sendInvite(data: { email: string; role?: string; facility_ids?: string[] }) {
    return this.request<{ id: string; token: string; email: string; role: string; expires_at: string }>('/auth/invites', { method: 'POST', body: data })
  }

  async listInvites() {
    return this.request<{ invites: InviteRecord[]; total: number }>('/auth/invites')
  }

  async revokeInvite(inviteId: string) {
    return this.request(`/auth/invites/${inviteId}`, { method: 'DELETE' })
  }

  async verifyInviteToken(token: string) {
    return this.request<{ email: string; role: string; org_name: string; expires_at: string }>(`/auth/invites/verify?token=${token}`)
  }

  async acceptInvite(data: { token: string; full_name: string; password: string }) {
    return this.request<{ access_token: string; refresh_token: string }>('/auth/invites/accept', { method: 'POST', body: data })
  }

  async requestPasswordReset(email: string) {
    return this.request<{ message: string }>('/auth/password-reset/request', { method: 'POST', body: { email } })
  }

  async confirmPasswordReset(token: string, password: string) {
    return this.request<{ message: string }>('/auth/password-reset/confirm', { method: 'POST', body: { token, password } })
  }

  async changePassword(currentPassword: string, newPassword: string) {
    return this.request<{ message: string }>('/auth/me/password', { method: 'POST', body: { current_password: currentPassword, new_password: newPassword } })
  }

  async updateMember(userId: string, data: { role?: string; is_active?: boolean; full_name?: string; facility_ids?: string[] }) {
    return this.request<OrgMember>(`/auth/members/${userId}`, { method: 'PATCH', body: data })
  }

  async removeMember(userId: string) {
    return this.request(`/auth/members/${userId}`, { method: 'DELETE' })
  }

  // ── Compressors ─────────────────────────────
  async listCompressors(facilityId: string) {
    return this.request<{ compressors: Compressor[]; total: number }>(`/facilities/${facilityId}/compressors`)
  }

  async createCompressor(facilityId: string, data: Record<string, unknown>) {
    return this.request<Compressor>(`/facilities/${facilityId}/compressors`, { method: 'POST', body: data })
  }

  async updateCompressor(facilityId: string, compressorId: string, data: Record<string, unknown>) {
    return this.request<Compressor>(`/facilities/${facilityId}/compressors/${compressorId}`, { method: 'PATCH', body: data })
  }

  async deleteCompressor(facilityId: string, compressorId: string) {
    return this.request(`/facilities/${facilityId}/compressors/${compressorId}`, { method: 'DELETE' })
  }

  async getCompressorSummary(facilityId: string) {
    return this.request<FacilityCompressorSummary>(`/facilities/${facilityId}/compressors/summary`)
  }

  async getCompressorReadings(facilityId: string, compressorId: string, hours = 24) {
    return this.request<{ readings: CompressorReading[]; total: number }>(
      `/facilities/${facilityId}/compressors/${compressorId}/readings?hours=${hours}`
    )
  }

  async triggerHealthCheck(facilityId: string, compressorId: string) {
    return this.request<{ compressor_id: string; health_score: number | null; anomalies: string[] }>(
      `/facilities/${facilityId}/compressors/${compressorId}/health-check`, { method: 'POST' }
    )
  }

  async getHealthTrend(facilityId: string, compressorId: string, days = 30) {
    return this.request<CompressorHealthTrend>(
      `/facilities/${facilityId}/compressors/${compressorId}/health-trend?days=${days}`
    )
  }

  // ── Live Monitor ────────────────────────────
  async getLiveMonitor() {
    return this.request<LiveMonitorResponse>('/live-monitor')
  }

  // ── Plant Control ───────────────────────────
  async controlCompressor(facilityId: string, body: Record<string, unknown>) {
    return this.request<{ status: string; command_id: string; action: string; compressor: string; message: string }>(
      `/facilities/${facilityId}/control/compressor`, { method: 'POST', body }
    )
  }

  async triggerDefrost(facilityId: string, body: Record<string, unknown>) {
    return this.request<{ status: string; command_id: string }>(
      `/facilities/${facilityId}/control/defrost`, { method: 'POST', body }
    )
  }

  async activateDemandResponse(facilityId: string, body: Record<string, unknown>) {
    return this.request<{ status: string; command_id: string }>(
      `/facilities/${facilityId}/control/demand-response`, { method: 'POST', body }
    )
  }

  async adjustZoneSetpoint(facilityId: string, body: Record<string, unknown>) {
    return this.request<{ status: string; zone: string; old_setpoint: number; new_setpoint: number }>(
      `/facilities/${facilityId}/control/zone-setpoint`, { method: 'POST', body }
    )
  }

  async getControlCapabilities(facilityId: string) {
    return this.request<ControlCapabilities>(`/facilities/${facilityId}/control/capabilities`)
  }

  async getControlAuditLog(facilityId: string, limit = 50) {
    return this.request<{ logs: ControlAuditEntry[]; total: number }>(
      `/facilities/${facilityId}/control/audit-log?limit=${limit}`
    )
  }

  async listPlantCommands(facilityId: string, state?: string) {
    const qs = state ? `?state=${state}` : ''
    return this.request<{ commands: PlantCommand[]; total: number }>(
      `/facilities/${facilityId}/control/commands${qs}`
    )
  }

  async cancelPlantCommand(facilityId: string, commandId: string) {
    return this.request<{ status: string; command_id: string }>(
      `/facilities/${facilityId}/control/commands/${commandId}/cancel`, { method: 'POST' }
    )
  }

  async approvePlantCommand(facilityId: string, commandId: string) {
    return this.request<{ status: string; command_id: string }>(
      `/facilities/${facilityId}/control/commands/${commandId}/approve`, { method: 'POST' }
    )
  }

  // ── Tariffs / Rate Schedules ────────────────
  async listUtilities() {
    return this.request<{ utilities: UtilityRecord[]; total: number }>(`/tariffs/utilities`)
  }

  async createUtility(data: { name: string; state?: string; iso_region?: string; regulated?: boolean }) {
    return this.request<UtilityRecord>(`/tariffs/utilities`, { method: 'POST', body: data })
  }

  async listRateSchedules(utilityId?: string) {
    const qs = utilityId ? `?utility_id=${utilityId}` : ''
    return this.request<{ rate_schedules: RateScheduleRecord[]; total: number }>(`/tariffs/rate-schedules${qs}`)
  }

  async createRateSchedule(data: Record<string, unknown>) {
    return this.request<RateScheduleRecord>(`/tariffs/rate-schedules`, { method: 'POST', body: data })
  }

  async updateRateSchedule(scheduleId: string, data: Record<string, unknown>) {
    return this.request<RateScheduleRecord>(`/tariffs/rate-schedules/${scheduleId}`, { method: 'PATCH', body: data })
  }

  async deleteRateSchedule(scheduleId: string) {
    return this.request(`/tariffs/rate-schedules/${scheduleId}`, { method: 'DELETE' })
  }

  async assignRateSchedule(facilityId: string, scheduleId: string) {
    return this.request(`/facilities/${facilityId}/rate-schedule/${scheduleId}`, { method: 'POST' })
  }

  // ── Energy Optimization ─────────────────────
  async getCurrentRate(facilityId: string) {
    return this.request<{ energy_rate: number; energy_period: string; demand_rate: number; demand_period: string; schedule_name: string }>(
      `/facilities/${facilityId}/energy/current-rate`
    )
  }

  async getRateWindows(facilityId: string, targetDate?: string) {
    const qs = targetDate ? `?target_date=${targetDate}` : ''
    return this.request<{ facility_id: string; date: string; schedule_name: string; windows: RateWindow[] }>(
      `/facilities/${facilityId}/energy/rate-windows${qs}`
    )
  }

  async getPrecoolSchedule(facilityId: string, targetDate?: string) {
    const qs = targetDate ? `?target_date=${targetDate}` : ''
    return this.request<PrecoolSchedule>(`/facilities/${facilityId}/energy/precool-schedule${qs}`)
  }

  async getDemandForecast(facilityId: string) {
    return this.request<DemandForecast>(`/facilities/${facilityId}/energy/demand-forecast`)
  }

  async getSavingsProjection(facilityId: string) {
    return this.request<SavingsProjection>(`/facilities/${facilityId}/energy/savings-projection`)
  }

  // ── Activity Log ─────────────────────────────
  async getActivityLog(params?: {
    resource_type?: string; action?: string; facility_id?: string;
    actor_id?: string; days?: number; limit?: number; offset?: number;
  }) {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null) qs.set(k, String(v))
      })
    }
    return this.request<ActivityLogResponse>(`/activity?${qs}`)
  }

  async getActivityStats(days = 30) {
    return this.request<ActivityStats>(`/activity/stats?days=${days}`)
  }

  async getActivityResourceTypes() {
    return this.request<{ resource_types: string[] }>('/activity/resource-types')
  }

  // ── Data Export ─────────────────────────────
  async exportPowerCSV(facilityId: string, params?: { start?: string; end?: string; interval?: string }) {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) qs.set(k, String(v))
      })
    }
    return this.request<{ csv: string }>(`/facilities/${facilityId}/reports/power/export?${qs}`)
  }

  async exportAuditCSV(facilityId: string, params?: { start?: string; end?: string }) {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) qs.set(k, String(v))
      })
    }
    return this.request<{ csv: string }>(`/facilities/${facilityId}/reports/audit-log/export?${qs}`)
  }

  async exportAlertsCSV(facilityId: string, params?: { state?: string; severity?: string }) {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) qs.set(k, String(v))
      })
    }
    return this.request<{ csv: string }>(`/facilities/${facilityId}/alerts/export?${qs}`)
  }

  // ── Dashboard Preferences ─────────────────
  async getDashboardLayout() {
    return this.request<DashboardLayout>('/auth/me/dashboard')
  }

  async saveDashboardLayout(layout: DashboardLayout) {
    return this.request<DashboardLayout>('/auth/me/dashboard', { method: 'PUT', body: layout })
  }

  // ── SSE helper ──────────────────────────────
  getEventStreamUrl(): string {
    return `${API_BASE}/events/stream?token=${this.token}`
  }

  // ── Compliance ─────────────────────────────
  async createCCP(data: Record<string, unknown>) {
    return this.request<CCP>('/compliance/ccps', { method: 'POST', body: data })
  }

  async listCCPs(facilityId?: string, activeOnly = true) {
    const qs = new URLSearchParams()
    if (facilityId) qs.set('facility_id', facilityId)
    if (!activeOnly) qs.set('active_only', 'false')
    return this.request<{ ccps: CCP[]; total: number }>(`/compliance/ccps?${qs}`)
  }

  async getCCP(ccpId: string) {
    return this.request<CCP>(`/compliance/ccps/${ccpId}`)
  }

  async updateCCP(ccpId: string, data: Record<string, unknown>) {
    return this.request<CCP>(`/compliance/ccps/${ccpId}`, { method: 'PATCH', body: data })
  }

  async deleteCCP(ccpId: string) {
    return this.request(`/compliance/ccps/${ccpId}`, { method: 'DELETE' })
  }

  async listComplianceLogs(params?: { facility_id?: string; ccp_id?: string; status?: string; hours?: number }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ logs: ComplianceLogEntry[]; total: number }>(`/compliance/logs?${qs}`)
  }

  async createManualCheck(data: { ccp_id: string; facility_id: string; temperature: number; temp_unit?: string }) {
    return this.request<ComplianceLogEntry>('/compliance/logs', { method: 'POST', body: data })
  }

  async listExcursions(params?: { facility_id?: string; state?: string; severity?: string; days?: number }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ excursions: TempExcursionEntry[]; total: number }>(`/compliance/excursions?${qs}`)
  }

  async resolveExcursion(excursionId: string, data: { state: string; corrective_action_taken?: string; notes?: string }) {
    return this.request<TempExcursionEntry>(`/compliance/excursions/${excursionId}`, { method: 'PATCH', body: data })
  }

  async generateComplianceReport(data: { facility_id: string; report_type?: string; title?: string }) {
    return this.request<ComplianceReportEntry>('/compliance/reports/generate', { method: 'POST', body: data })
  }

  async listComplianceReports(params?: { facility_id?: string; report_type?: string; state?: string }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ reports: ComplianceReportEntry[]; total: number }>(`/compliance/reports?${qs}`)
  }

  async getComplianceReport(reportId: string) {
    return this.request<ComplianceReportEntry>(`/compliance/reports/${reportId}`)
  }

  async signOffReport(reportId: string, data?: { sign_off_notes?: string }) {
    return this.request<ComplianceReportEntry>(`/compliance/reports/${reportId}/sign-off`, { method: 'PATCH', body: data || {} })
  }

  async getComplianceDashboard(facilityId?: string) {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<ComplianceDashboard>(`/compliance/dashboard${qs}`)
  }

  // ── Maintenance ────────────────────────────
  async createMaintenanceTask(data: Record<string, unknown>) {
    return this.request<MaintenanceTaskEntry>('/maintenance/tasks', { method: 'POST', body: data })
  }

  async createWorkOrderFromAlert(alertId: string) {
    return this.request<MaintenanceTaskEntry>('/maintenance/tasks/from-alert', { method: 'POST', body: { alert_id: alertId } })
  }

  async createWorkOrderFromLeakEvent(leakEventId: string) {
    return this.request<MaintenanceTaskEntry>('/maintenance/tasks/from-leak-event', { method: 'POST', body: { leak_event_id: leakEventId } })
  }

  async listMaintenanceTasks(params?: {
    facility_id?: string; state?: string; category?: string;
    priority?: string; assigned_to?: string; limit?: number; offset?: number;
  }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ tasks: MaintenanceTaskEntry[]; total: number }>(`/maintenance/tasks?${qs}`)
  }

  async getMaintenanceTask(taskId: string) {
    return this.request<MaintenanceTaskEntry>(`/maintenance/tasks/${taskId}`)
  }

  async updateMaintenanceTask(taskId: string, data: Record<string, unknown>) {
    return this.request<MaintenanceTaskEntry>(`/maintenance/tasks/${taskId}`, { method: 'PATCH', body: data })
  }

  async cancelMaintenanceTask(taskId: string) {
    return this.request(`/maintenance/tasks/${taskId}`, { method: 'DELETE' })
  }

  async getMaintenanceDashboard(facilityId?: string) {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<MaintenanceDashboardStats>(`/maintenance/dashboard${qs}`)
  }

  async listOverdueTasks(facilityId?: string) {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<{ tasks: MaintenanceTaskEntry[]; total: number }>(`/maintenance/overdue${qs}`)
  }

  // ── Refrigerant Circuits ──────────────────
  listRacks(facilityId?: string): Promise<{ racks: RackTelemetry[] }> {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<{ racks: RackTelemetry[] }>(`/refrigerant/racks${qs}`)
  }

  listCircuits(facilityId?: string): Promise<{ circuits: RefrigerantCircuit[] }> {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<{ circuits: RefrigerantCircuit[] }>(`/refrigerant/circuits${qs}`)
  }

  createCircuit(data: Record<string, unknown>): Promise<RefrigerantCircuit> {
    return this.request<RefrigerantCircuit>('/refrigerant/circuits', { method: 'POST', body: data })
  }

  updateCircuit(id: string, data: Record<string, unknown>): Promise<RefrigerantCircuit> {
    return this.request<RefrigerantCircuit>(`/refrigerant/circuits/${id}`, { method: 'PATCH', body: data })
  }

  // ── Leak Events ───────────────────────────
  listLeakEvents(params?: { facility_id?: string; status?: string; limit?: number }): Promise<{ leak_events: LeakEvent[]; total: number }> {
    const query = new URLSearchParams()
    if (params?.facility_id) query.set('facility_id', params.facility_id)
    if (params?.status) query.set('status', params.status)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return this.request<{ leak_events: LeakEvent[]; total: number }>(`/refrigerant/leak-events${qs ? '?' + qs : ''}`)
  }

  createLeakEvent(data: Record<string, unknown>): Promise<LeakEvent> {
    return this.request<LeakEvent>('/refrigerant/leak-events', { method: 'POST', body: data })
  }

  updateLeakEvent(id: string, data: Record<string, unknown>): Promise<LeakEvent> {
    return this.request<LeakEvent>(`/refrigerant/leak-events/${id}`, { method: 'PATCH', body: data })
  }

  // ── Refrigerant Adds ──────────────────────
  listRefrigerantAdds(params?: { facility_id?: string; circuit_id?: string; limit?: number }): Promise<{ adds: RefrigerantAdd[]; total: number }> {
    const query = new URLSearchParams()
    if (params?.facility_id) query.set('facility_id', params.facility_id)
    if (params?.circuit_id) query.set('circuit_id', params.circuit_id)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return this.request<{ adds: RefrigerantAdd[]; total: number }>(`/refrigerant/adds${qs ? '?' + qs : ''}`)
  }

  createRefrigerantAdd(data: Record<string, unknown>): Promise<RefrigerantAdd> {
    return this.request<RefrigerantAdd>('/refrigerant/adds', { method: 'POST', body: data })
  }

  // ── Repairs ───────────────────────────────
  listRepairs(params?: { facility_id?: string; leak_event_id?: string; limit?: number }): Promise<{ repairs: RepairRecord[]; total: number }> {
    const query = new URLSearchParams()
    if (params?.facility_id) query.set('facility_id', params.facility_id)
    if (params?.leak_event_id) query.set('leak_event_id', params.leak_event_id)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return this.request<{ repairs: RepairRecord[]; total: number }>(`/refrigerant/repairs${qs ? '?' + qs : ''}`)
  }

  createRepair(data: Record<string, unknown>): Promise<RepairRecord> {
    return this.request<RepairRecord>('/refrigerant/repairs', { method: 'POST', body: data })
  }

  detectCallback(repairId: string): Promise<{ callback_detected: boolean | null; callback_lbs_within_30d?: number; reason?: string }> {
    return this.request(`/refrigerant/repairs/${repairId}/detect-callback`, { method: 'POST' })
  }

  // ── Dashboard + AIM Act ───────────────────
  getRefrigerantDashboard(facilityId?: string): Promise<RefrigerantDashboard> {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<RefrigerantDashboard>(`/refrigerant/dashboard${qs}`)
  }

  getAIMActSummary(facilityId?: string): Promise<AIMActSummary> {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<AIMActSummary>(`/refrigerant/aim-act${qs}`)
  }

  // ── Detection & Forecasting ───────────────
  getDetectionSettings(): Promise<DetectionSettings> {
    return this.request<DetectionSettings>('/detection/settings')
  }

  updateDetectionSettings(data: Partial<DetectionSettings>): Promise<DetectionSettings> {
    return this.request<DetectionSettings>('/detection/settings', { method: 'PATCH', body: data })
  }

  getDetectionForecasts(facilityId?: string): Promise<CircuitForecast[]> {
    const qs = facilityId ? `?facility_id=${facilityId}` : ''
    return this.request<CircuitForecast[]>(`/detection/forecasts${qs}`)
  }

  getDetectionInsights(facilityId?: string, days = 30): Promise<DetectionInsights> {
    const params = new URLSearchParams()
    if (facilityId) params.set('facility_id', facilityId)
    params.set('days', String(days))
    return this.request<DetectionInsights>(`/detection/insights?${params}`)
  }

  // ── Escalation ────────────────────────────
  async createEscalationPolicy(data: Record<string, unknown>) {
    return this.request<EscalationPolicyEntry>('/escalation/policies', { method: 'POST', body: data })
  }

  async listEscalationPolicies(activeOnly = true) {
    const qs = activeOnly ? '' : '?active_only=false'
    return this.request<{ policies: EscalationPolicyEntry[]; total: number }>(`/escalation/policies${qs}`)
  }

  async getEscalationPolicy(policyId: string) {
    return this.request<EscalationPolicyEntry>(`/escalation/policies/${policyId}`)
  }

  async updateEscalationPolicy(policyId: string, data: Record<string, unknown>) {
    return this.request<EscalationPolicyEntry>(`/escalation/policies/${policyId}`, { method: 'PATCH', body: data })
  }

  async deleteEscalationPolicy(policyId: string) {
    return this.request(`/escalation/policies/${policyId}`, { method: 'DELETE' })
  }

  async listEscalationEvents(params?: { alert_id?: string; policy_id?: string }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ events: EscalationEventEntry[]; total: number }>(`/escalation/events?${qs}`)
  }

  async testEscalation(policyId: string) {
    return this.request<{ policy: EscalationPolicyEntry; test_result: Record<string, unknown> }>(
      `/escalation/test/${policyId}`, { method: 'POST' }
    )
  }

  // ── Documents ─────────────────────────────
  async listDocuments(params?: { facility_id?: string; document_type?: string; limit?: number }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ documents: Document[]; total: number }>(`/documents?${qs}`)
  }

  async uploadDocument(file: File, metadata: { facility_id?: string; equipment_id?: string; document_type: string; name?: string }) {
    const formData = new FormData()
    formData.append('file', file)
    Object.entries(metadata).forEach(([k, v]) => { if (v) formData.append(k, v) })
    const upload = async (): Promise<Response> => {
      const headers: Record<string, string> = {}
      if (this.token) headers['Authorization'] = `Bearer ${this.token}`
      return fetch(`${API_BASE}/documents`, { method: 'POST', headers, body: formData })
    }
    let response = await upload()
    if (response.status === 401) {
      const newToken = await this.refreshAccessToken()
      if (newToken) response = await upload()
      else this.onUnauthorized?.()
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }
    return response.json() as Promise<Document>
  }

  async deleteDocument(documentId: string) {
    return this.request(`/documents/${documentId}`, { method: 'DELETE' })
  }

  // ── Tunnel Sessions ───────────────────────
  async listTunnelSessions(params?: { facility_id?: string; limit?: number }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ sessions: TunnelSession[]; total: number }>(`/tunnel/sessions?${qs}`)
  }

  async startTunnelSession(data: { facility_id: string; target_device?: string; notes?: string }) {
    return this.request<TunnelSession>('/tunnel/sessions', { method: 'POST', body: data })
  }

  async endTunnelSession(sessionId: string, data?: { end_reason?: string }) {
    return this.request<TunnelSession>(`/tunnel/sessions/${sessionId}/end`, { method: 'POST', body: data || {} })
  }

  // ── Maintenance Events ────────────────────
  async listMaintenanceEvents(params?: { facility_id?: string; event_type?: string; limit?: number }) {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)) })
    return this.request<{ events: MaintenanceEventEntry[]; total: number }>(`/maintenance/events?${qs}`)
  }

  async createMaintenanceEvent(data: {
    facility_id: string
    equipment_id?: string
    event_type: string
    description: string
    technician_name: string
    technician_company?: string
    occurred_at?: string
    linked_alert_id?: string
    linked_refrigerant_event_id?: string
  }) {
    return this.request<MaintenanceEventEntry>('/maintenance/events', { method: 'POST', body: data })
  }
}

// ── Types ───────────────────────────────────────

export interface Facility {
  id: string
  name: string
  address: string | null
  city: string | null
  state: string | null
  sqft: number | null
  zone_types: string[] | null
  utility_id: string | null
  rate_schedule_id: string | null
  iso_region: string | null
  latitude: number | null
  longitude: number | null
  floor_plan: FloorPlanData | null
  created_at: string
}

export interface FloorPlanElement {
  id: string
  type: 'zone' | 'compressor' | 'equipment' | 'label' | 'wall'
  x: number
  y: number
  width: number
  height: number
  label: string
  ref_id?: string  // zone_id, compressor_id, equipment_id
  config?: Record<string, unknown>  // color, icon, rotation, etc.
}

export interface FloorPlanData {
  canvas: { width: number; height: number; background: string; grid_size: number }
  elements: FloorPlanElement[]
}

export interface Bill {
  id: string
  facility_id: string
  period_start: string
  period_end: string
  total_kwh: number | null
  total_cost: number | null
  peak_demand_kw: number | null
  demand_charge: number | null
  energy_charge: number | null
  source_file: string | null
  parsed_at: string | null
  raw_data: Record<string, unknown> | null
  created_at: string
}

export interface DemandAnalysis {
  id: string
  facility_id: string
  period_start: string
  period_end: string
  peak_demand_kw: number | null
  peak_demand_time: string | null
  ratchet_demand_kw: number | null
  demand_charge_actual: number | null
  demand_charge_optimized: number | null
  savings_potential: number | null
  peak_events: Record<string, unknown> | null
  load_profile: Record<string, unknown> | null
  created_at: string
}

export interface Equipment {
  id: string
  facility_id: string
  name: string
  equipment_type: string
  manufacturer: string | null
  model: string | null
  controller_type: string | null
  protocol: string | null
  commissioned_at: string | null
  created_at: string
}

export interface Zone {
  id: string
  facility_id: string
  name: string
  zone_type: string
  area_sqft: number | null
  position_x: number | null
  position_y: number | null
  width: number | null
  height: number | null
  temp_setpoint: number | null
  temp_unit: string
  temp_tolerance: number
  temp_alarm_high: number | null
  temp_alarm_low: number | null
  humidity_setpoint: number | null
  humidity_alarm_high: number | null
  current_temp: number | null
  current_humidity: number | null
  door_open: boolean
  state: string
  last_reading_at: string | null
  created_at: string
}

export interface ZoneCreate {
  name: string
  zone_type: string
  area_sqft?: number
  position_x?: number
  position_y?: number
  width?: number
  height?: number
  temp_setpoint?: number
  temp_unit?: string
  temp_tolerance?: number
  temp_alarm_high?: number
  temp_alarm_low?: number
  humidity_setpoint?: number
  humidity_alarm_high?: number
}

export interface Alert {
  id: string
  facility_id: string
  zone_id: string | null
  equipment_id: string | null
  agent_id: string | null
  severity: string
  category: string
  alert_type: string
  title: string
  message: string | null
  state: string
  acknowledged_by: string | null
  acknowledged_at: string | null
  resolved_at: string | null
  trigger_value: number | null
  threshold_value: number | null
  context: Record<string, unknown> | null
  triggered_at: string
  created_at: string
}

export interface EventRecord {
  id: string
  facility_id: string
  event_type: string
  source: string
  description: string
  data: Record<string, unknown> | null
  occurred_at: string
}

export interface ControlSequence {
  id: string
  facility_id: string
  name: string
  description: string | null
  sequence_type: string
  enabled: boolean
  priority: number
  steps: Record<string, unknown>[]
  conditions: Record<string, unknown> | null
  last_run_at: string | null
  last_result: string | null
  run_count: number
  created_at: string
}

export interface SequenceCreate {
  name: string
  description?: string
  sequence_type: string
  priority?: number
  steps: Record<string, unknown>[]
  conditions?: Record<string, unknown>
}

export interface AutomationRule {
  id: string
  facility_id: string
  name: string
  description: string | null
  enabled: boolean
  trigger_conditions: Record<string, unknown>
  actions: Record<string, unknown>[]
  cooldown_minutes: number
  max_executions_per_day: number
  execution_count_today: number
  last_triggered_at: string | null
  created_at: string
}

export interface AutomationRuleCreate {
  name: string
  description?: string
  enabled?: boolean
  trigger_conditions: Record<string, unknown>
  actions: Record<string, unknown>[]
  cooldown_minutes?: number
  max_executions_per_day?: number
}

export interface ScheduleCreate {
  control_sequence_id: string
  name: string
  schedule_type: string // daily, weekly, cron, one_time
  cron_expression?: string
  days_of_week?: number[]
  start_time?: string
  end_time?: string
  timezone?: string
}

export interface ScheduleRecord {
  id: string
  facility_id: string
  control_sequence_id: string
  name: string
  enabled: boolean
  schedule_type: string
  cron_expression: string | null
  timezone: string
  next_run_at: string | null
  last_run_at: string | null
  created_at: string
}

export interface Command {
  id: string
  facility_id: string
  agent_id: string
  command_type: string
  parameters: Record<string, unknown>
  state: string
  priority: number
  issued_at: string
  completed_at: string | null
  error_message: string | null
}

export interface EdgeAgent {
  id: string
  facility_id: string
  name: string
  agent_key: string
  version: string | null
  hardware_type: string | null
  hostname: string | null
  ip_address: string | null
  connection_state: string
  last_heartbeat: string | null
  last_telemetry_at: string | null
  cpu_percent: number | null
  memory_percent: number | null
  disk_percent: number | null
  uptime_seconds: number | null
  enabled: boolean
  config_version: number
  pending_commands: number
  registered_at: string
}

export interface DeviceProfile {
  id: string
  manufacturer: string
  model: string
  display_name: string
  description: string | null
  equipment_type: string
  refrigerant_types: string[]
  protocol: string
  default_port: number
  default_slave_id: number
  register_map: Record<string, {
    register: number
    type: string
    data_type: string
    scale: number
    offset: number
    unit: string
    description: string
  }>
  is_builtin: boolean
  is_active: boolean
  version: number
  created_at: string
}

export interface AgentDevice {
  id: string
  agent_id: string
  profile_id: string | null
  compressor_id: string | null
  name: string
  host: string
  port: number
  slave_id: number
  register_overrides: Record<string, unknown> | null
  poll_interval_sec: number
  enabled: boolean
  connection_state: string
  last_poll_at: string | null
  last_success_at: string | null
  last_error: string | null
  poll_count: number
  error_count: number
  created_at: string
}

export interface AgentConfigBundle {
  agent_name: string
  agent_key: string
  platform_url: string
  heartbeat_interval_sec: number
  devices: Array<{
    name: string
    host: string
    port: number
    slave_id: number
    poll_interval_sec: number
    protocol: string
    compressor_id: string | null
    registers: Record<string, unknown>
  }>
}

export interface DiscoveredDevice {
  host: string
  port: number
  protocol: string
  slave_id: number
  responding: boolean
  device_info: {
    vendor?: string
    product_code?: string
    firmware_version?: string
    serial?: string
  }
  matched_profile?: string
  matched_profile_id?: string | null
  matched_manufacturer?: string
  matched_refrigerants?: string[]
  sample_values?: Record<string, number>
  already_provisioned?: boolean
  provisioned?: boolean
  compressor_id?: string
  device_id?: string
}

export interface DiscoveryResult {
  agent_id: string
  scan_timestamp: string | null
  subnet: string | null
  total_found: number
  devices: DiscoveredDevice[]
}

export interface SavingsResult {
  facility_id: string
  facility_name: string
  summary: {
    bills_analyzed: number
    avg_peak_demand_kw: number
    avg_demand_charge: number
    effective_demand_rate: number
    combined_monthly_savings: number
    combined_annual_savings: number
  }
  scenarios: Array<{
    scenario: string
    current_peak_kw: number
    reduced_peak_kw: number
    reduction_kw: number
    monthly_savings: number
    annual_savings: number
    implementation: string
  }>
  ratchet_analysis: {
    months_affected: number
    total_ratchet_penalty: number
    annual_ratchet_cost: number
  } | null
}

export interface SavingsReport {
  facility_id: string
  facility_name: string
  report_period: { start: string; end: string }
  energy_savings: {
    available: boolean
    bills_analyzed: number
    annual_bill_total: number
    demand_savings_est: number
    energy_savings_est: number
    total_est: number
    demand_reduction_pct: number
    energy_reduction_pct: number
  }
  refrigerant_savings: {
    total_lbs_added_12m: number
    refrigerant_cost_12m: number
    charge_deficit_pct: number
    energy_penalty_pct: number
    refrigerant_energy_penalty_cost: number
    total_refrigerant_impact: number
  }
  total_quantified_savings: number
  methodology: {
    demand_response: string
    energy_optimization: string
    refrigerant_efficiency: string
    refrigerant_cost: string
  }
}

// ── Integration Types ──────────────────────────────────

export interface IntegrationProvider {
  provider: string
  integration_type: string
  supports_write: boolean
}

export interface IntegrationRecord {
  id: string
  facility_id: string
  provider: string
  integration_type: string
  name: string
  description: string | null
  config: Record<string, unknown>
  credential_id: string | null
  enabled: boolean
  connection_state: string
  last_poll_at: string | null
  last_success_at: string | null
  last_error: string | null
  last_error_at: string | null
  total_polls: number
  total_errors: number
  total_readings_ingested: number
  device_map: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface IntegrationCredentialRecord {
  id: string
  facility_id: string
  provider: string
  auth_type: string
  token_expires_at: string | null
  last_refreshed_at: string | null
  created_at: string
}

export interface IntegrationDiscoveredDevice {
  external_id: string
  name: string
  device_type: string
  manufacturer: string | null
  model: string | null
  protocol: string | null
  address: string | null
  metadata: Record<string, unknown>
  available_metrics: string[]
}

export interface RegisterMapRecord {
  id: string
  name: string
  protocol: string
  manufacturer: string
  model: string | null
  description: string | null
  version: string
  registers: Record<string, unknown>
  created_at: string
}

// ── Notification Types ──────────────────────────────
export interface NotificationChannelRecord {
  id: string
  org_id: string
  name: string
  channel_type: string
  config: Record<string, unknown>
  enabled: boolean
  facility_ids: string[] | null
  min_severity: string | null
  categories: string[] | null
  created_at: string
}

export interface NotificationChannelCreate {
  name: string
  channel_type: string
  config?: Record<string, unknown>
  enabled?: boolean
  facility_ids?: string[] | null
  min_severity?: string | null
  categories?: string[] | null
}

export interface NotificationPolicy {
  id: string
  org_id: string
  user_id: string | null
  name: string
  facility_ids: string[] | null
  categories: string[] | null
  min_severity: string
  channel_ids: string[] | null
  quiet_hours_enabled: boolean
  quiet_hours_start: number
  quiet_hours_end: number
  quiet_hours_bypass_severity: string | null
  cooldown_minutes: number
  digest_mode: boolean
  digest_interval_hours: number
  escalation_enabled: boolean
  escalation_delay_minutes: number
  escalation_channel_ids: string[] | null
  escalation_min_severity: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface NotificationPolicyCreate {
  name?: string
  facility_ids?: string[] | null
  categories?: string[] | null
  min_severity?: string
  channel_ids?: string[] | null
  quiet_hours_enabled?: boolean
  quiet_hours_start?: number
  quiet_hours_end?: number
  quiet_hours_bypass_severity?: string | null
  cooldown_minutes?: number
  digest_mode?: boolean
  digest_interval_hours?: number
  escalation_enabled?: boolean
  escalation_delay_minutes?: number
  escalation_channel_ids?: string[] | null
  escalation_min_severity?: string
  enabled?: boolean
}

export interface NotificationLogRecord {
  id: string
  org_id: string
  channel_id: string | null
  facility_id: string | null
  subject: string
  body: string
  channel_type: string
  status: string
  error_message: string | null
  sent_at: string
}

// ── User/Org Types ─────────────────────────────────
export type UserRole =
  | 'kelvex_admin'
  | 'owner'
  | 'admin'
  | 'finance'
  | 'ops_manager'
  | 'technician'
  | 'plant_manager'   // legacy
  | 'operator'        // legacy
  | 'viewer'          // legacy

export const ROLE_LABELS: Record<UserRole, string> = {
  kelvex_admin: 'Kelvex Admin',
  owner: 'Owner',
  admin: 'Admin',
  finance: 'Finance',
  ops_manager: 'Operations Manager',
  technician: 'Technician',
  plant_manager: 'Plant Manager',
  operator: 'Operator',
  viewer: 'Viewer',
}

export const ROLE_ORDER: UserRole[] = [
  'kelvex_admin', 'owner', 'admin', 'finance', 'ops_manager',
  'technician', 'plant_manager', 'operator', 'viewer',
]

export const GLOBAL_ACCESS_ROLES: UserRole[] = ['kelvex_admin', 'owner', 'admin']

/** Returns the default landing route for a given role. */
export function roleHome(role: UserRole): string {
  switch (role) {
    case 'finance':    return '/energy'
    case 'technician': return '/sites'
    case 'kelvex_admin': return '/admin'
    default:           return '/'
  }
}

export interface FacilityAccess {
  facility_id: string
  facility_name: string | null
}

export interface OrgMember {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  facility_access: FacilityAccess[]
}

export interface InviteRecord {
  id: string
  token: string
  email: string
  role: string
  facility_ids: string[] | null
  expires_at: string
  used_at: string | null
  created_at: string
  is_valid: boolean
}

// ── Compressor Types ──────────────────────────────
export interface Compressor {
  id: string
  facility_id: string
  name: string
  tag: string | null
  manufacturer: string | null
  model: string | null
  serial_number: string | null
  compressor_type: string
  refrigerant: string
  refrigerant_charge_lbs: number | null
  hp: number | null
  capacity_tons: number | null
  design_suction_psi: number | null
  design_discharge_psi: number | null
  max_discharge_temp_f: number | null
  alarm_discharge_psi_high: number | null
  alarm_suction_psi_low: number | null
  alarm_oil_temp_high: number | null
  alarm_bearing_temp_high: number | null
  alarm_vibration_high: number | null
  alarm_amp_draw_high: number | null
  commissioned_at: string | null
  last_overhaul_at: string | null
  run_hours: number | null
  next_maintenance_hours: number | null
  state: string
  health_score: number | null
  last_reading_at: string | null
  rack_name: string | null
  created_at: string
  updated_at: string
}

export interface CompressorReading {
  id: string
  compressor_id: string
  discharge_pressure_psi: number | null
  suction_pressure_psi: number | null
  discharge_temp_f: number | null
  suction_temp_f: number | null
  oil_pressure_psi: number | null
  oil_temp_f: number | null
  bearing_temp_f: number | null
  amp_draw: number | null
  kw: number | null
  power_factor: number | null
  vibration_ips: number | null
  slide_valve_pct: number | null
  rpm: number | null
  superheat_f: number | null
  subcooling_f: number | null
  compression_ratio: number | null
  efficiency_pct: number | null
  running: boolean | null
  alarm_active: boolean
  alarm_codes: string[] | null
  recorded_at: string
}

export interface CompressorHealthSummary {
  compressor_id: string
  name: string
  tag: string | null
  manufacturer: string | null
  model: string | null
  state: string
  health_score: number | null
  refrigerant: string
  hp: number | null
  rack_name: string | null
  discharge_pressure_psi: number | null
  suction_pressure_psi: number | null
  oil_temp_f: number | null
  bearing_temp_f: number | null
  vibration_ips: number | null
  amp_draw: number | null
  kw: number | null
  slide_valve_pct: number | null
  running: boolean | null
  last_reading_at: string | null
  anomalies: string[]
}

export interface FacilityCompressorSummary {
  facility_id: string
  total_compressors: number
  running: number
  in_alarm: number
  avg_health_score: number | null
  total_kw: number | null
  total_capacity_tons: number | null
  compressors: CompressorHealthSummary[]
}

// ── Rate Schedule Types ───────────────────────────
export interface RateScheduleRecord {
  id: string
  utility_id: string
  openei_rate_id: string | null
  schedule_name: string
  description: string | null
  sector: string
  effective_date: string
  end_date: string | null
  demand_rates: Record<string, unknown>
  energy_rates: Record<string, unknown>
  fixed_charges: Record<string, unknown> | null
  created_at: string
}

export interface UtilityRecord {
  id: string
  name: string
  state: string | null
  iso_region: string | null
  regulated: boolean
  created_at: string
}

// ── Energy Types ──────────────────────────────────
export interface RateWindow {
  hour: number
  energy_period: string
  energy_rate: number
  demand_rate: number
}

export interface PrecoolSchedule {
  facility_id: string
  target_date: string
  rate_schedule: string
  rate_windows: RateWindow[]
  on_peak_hours: number[]
  off_peak_hours: number[]
  precool_window: { start_hour: number | null; end_hour: number | null; hours: number[] }
  coast_window: { hours: number[] }
  plant_summary: { total_compressors: number; total_hp: number; total_capacity_tons: number; estimated_load_kw: number }
  zone_strategies: { zone_id: string; zone_name: string; zone_type: string; current_setpoint: number; precool_target: number; temp_delta: number; precool_hours: number[]; coast_hours: number[] }[]
  estimated_savings: { energy_savings_daily: number; energy_savings_monthly: number; demand_reduction_pct: number; rate_differential: number; shifted_kwh_daily: number }
}

export interface DemandForecast {
  facility_id: string
  billing_cycle: { start: string; end: string; days_total: number; days_elapsed: number; pct_elapsed: number }
  demand: { current_peak_kw: number; ratchet_demand_kw: number; billed_demand_kw: number; demand_rate_per_kw: number; projected_charge: number }
  risk: { level: string; message: string; pct_of_historical_peak: number }
  historical_peaks: { period: string; peak_kw: number }[]
  ratchet: Record<string, unknown> | null
}

export interface SavingsProjection {
  facility_id: string
  current_costs: { annual_total: number; annual_demand: number; annual_energy: number; avg_peak_kw: number; bills_analyzed: number }
  projected_savings: { annual_total: number; monthly_avg: number; demand_savings: number; energy_savings: number; demand_reduction_pct: number; energy_reduction_pct: number }
  plant_capacity: { total_compressors: number; total_hp: number; estimated_load_kw: number | null }
}

// ── Plant Control Types ──────────────────────────

export interface ControlParamOption {
  value: string
  label: string
}

export interface ControlParamDef {
  type: 'slider' | 'number' | 'select' | 'toggle'
  label: string
  unit?: string
  min?: number
  max?: number
  step?: number
  default?: unknown
  options?: ControlParamOption[]
  description?: string
  register?: string
  required?: boolean
  visible_when?: Record<string, string>
}

export interface ControlActionSchema {
  label: string
  icon?: string
  description?: string
  scope?: 'facility' | 'compressor'
  params: Record<string, ControlParamDef>
}

export interface ControlCapabilities {
  facility_id: string
  has_agent: boolean
  agent_connected: boolean
  compressors: {
    compressor_id: string
    name: string
    state: string
    writable_registers: string[]
    can_set_capacity: boolean
    can_start_stop: boolean
    can_set_suction: boolean
    has_defrost_config: boolean
    control_schemas?: Record<string, ControlActionSchema>
  }[]
  zones: { zone_id: string; name: string; type: string; current_temp: number | null; setpoint: number | null }[]
  facility_control_schemas?: Record<string, ControlActionSchema>
  features: {
    capacity_control: boolean
    start_stop: boolean
    suction_setpoint: boolean
    defrost_control: boolean
    demand_response: boolean
    zone_setpoint: boolean
  }
}

export interface ControlAuditEntry {
  id: string
  action: string
  target_type: string
  target_name: string | null
  parameters: Record<string, unknown> | null
  result: string | null
  created_at: string | null
}

export interface CompressorHealthTrend {
  compressor_id: string
  compressor_name: string
  current_health_score: number | null
  trend_slope_per_day: number | null
  days_to_maintenance_threshold: number | null
  projected_maintenance_date: string | null
  maintenance_urgency: 'immediate' | 'soon' | 'monitor' | 'healthy'
  daily_scores: { date: string | null; score: number | null; reading_count: number }[]
}

export interface PlantCommand {
  id: string
  command_type: string
  parameters: Record<string, unknown>
  state: string
  priority: number
  source: string
  issued_at: string | null
  completed_at: string | null
  error_message: string | null
}

// ── Live Monitor Types ───────────────────────────
export interface LiveCompressorReadings {
  discharge_pressure_psi: number | null
  suction_pressure_psi: number | null
  discharge_temp_f: number | null
  oil_temp_f: number | null
  bearing_temp_f: number | null
  vibration_ips: number | null
  amp_draw: number | null
  kw: number | null
  slide_valve_pct: number | null
  rpm: number | null
  running: boolean | null
  compression_ratio: number | null
  recorded_at: string | null
}

export interface LiveCompressor {
  id: string
  name: string
  tag: string | null
  manufacturer: string | null
  model: string | null
  state: string
  health_score: number | null
  refrigerant: string
  hp: number | null
  rack_name: string | null
  data_stale: boolean
  anomalies: { type: string; value: number; threshold: number }[]
  readings: LiveCompressorReadings
}

export interface LiveFacility {
  facility_id: string
  facility_name: string
  location: string | null
  agent_status: string
  last_heartbeat: string | null
  total_compressors: number
  running: number
  in_alarm: number
  total_kw: number | null
  compressors: LiveCompressor[]
}

export interface LiveMonitorResponse {
  timestamp: string
  org_summary: {
    total_facilities: number
    total_compressors: number
    running: number
    in_alarm: number
    offline_agents: number
    total_kw: number | null
  }
  facilities: LiveFacility[]
}

// ── Report Types ────────────────────────────────────
export interface PowerDataPoint {
  time: string
  total_kw: number
  avg_kw: number
  peak_kw: number
  kwh_estimate: number
  equipment_count: number
}

export interface PowerReport {
  facility_id: string
  start: string
  end: string
  interval: string
  total_kwh: number
  peak_demand_kw: number
  data_points: PowerDataPoint[]
  count: number
}

export interface EquipmentPowerBreakdown {
  equipment_id: string
  name: string
  equipment_type: string
  avg_kw: number
  peak_kw: number
  readings: number
}

export interface PowerSummary {
  facility_id: string
  days: number
  avg_kw: number
  peak_kw: number
  min_kw: number
  estimated_kwh: number
  reading_count: number
  equipment_breakdown: EquipmentPowerBreakdown[]
}

export interface AuditCommand {
  id: string
  command_type: string
  state: string
  parameters: Record<string, unknown>
  priority: number
  target_equipment_id: string | null
  target_zone_id: string | null
  agent_id: string
  issued_by: string | null
  issued_at: string | null
  sent_at: string | null
  completed_at: string | null
  error_message: string | null
  result: Record<string, unknown> | null
}

export interface AuditLogReport {
  facility_id: string
  start: string
  end: string
  total: number
  by_state: Record<string, number>
  by_type: Record<string, number>
  commands: AuditCommand[]
}

export interface DigestPreview {
  period_hours: number
  since: string
  facilities_count: number
  facilities: { id: string; name: string }[]
  alerts: {
    new_total: number
    active_by_severity: Record<string, number>
  }
  commands: {
    total: number
    completed: number
    failed: number
  }
  automation: {
    rule_fires_today: number
  }
  notifications: Record<string, number>
}

// ── Activity Log types ──────────────────────────
export interface ActivityLogEntry {
  id: string
  action: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  facility_id: string | null
  actor_id: string | null
  actor_email: string | null
  summary: string | null
  changes: Record<string, { old: unknown; new: unknown }> | null
  ip_address: string | null
  created_at: string
}

export interface ActivityLogResponse {
  items: ActivityLogEntry[]
  total: number
  limit: number
  offset: number
}

export interface ActivityStats {
  total: number
  days: number
  by_action: Record<string, number>
  by_resource: Record<string, number>
  unique_actors: number
  top_actors: { email: string; count: number }[]
}

export interface DashboardWidget {
  id: string
  type: 'alerts' | 'power' | 'commands' | 'compressors' | 'zones' | 'savings' | 'custom'
  title: string
  size: 'sm' | 'md' | 'lg'
  config?: Record<string, unknown>
}

export interface DashboardLayout {
  widgets: DashboardWidget[]
}

// ── Compliance Types ────────────────────────────

export interface CCP {
  id: string
  facility_id: string
  org_id: string
  name: string
  description: string | null
  zone_id: string | null
  equipment_id: string | null
  metric_name: string
  temp_min: number
  temp_max: number
  temp_unit: string
  warning_offset: number
  check_interval_min: number
  excursion_threshold_min: number
  hazard_type: string | null
  corrective_action: string | null
  verification_method: string | null
  is_active: boolean
  created_at: string
}

export interface ComplianceLogEntry {
  id: string
  ccp_id: string
  facility_id: string
  temperature: number
  temp_unit: string
  status: 'pass' | 'warning' | 'critical' | 'no_data'
  limit_min: number
  limit_max: number
  checked_at: string
  source: string
}

export interface TempExcursionEntry {
  id: string
  ccp_id: string
  facility_id: string
  org_id: string
  severity: 'warning' | 'critical'
  peak_temp: number
  avg_temp: number | null
  limit_breached: 'high' | 'low'
  started_at: string
  ended_at: string | null
  duration_minutes: number | null
  state: 'active' | 'resolved' | 'acknowledged'
  corrective_action_taken: string | null
  resolved_by: string | null
  resolved_at: string | null
  notes: string | null
  created_at: string
}

export interface ComplianceReportEntry {
  id: string
  facility_id: string
  org_id: string
  report_type: string
  title: string
  period_start: string
  period_end: string
  total_checks: number
  passed_checks: number
  failed_checks: number
  excursion_count: number
  compliance_pct: number
  report_data: Record<string, unknown>
  generated_by: string | null
  signed_off_by: string | null
  signed_off_at: string | null
  sign_off_notes: string | null
  state: 'draft' | 'pending_review' | 'signed_off'
  created_at: string
}

export interface ComplianceDashboard {
  active_ccps: number
  checks_24h: number
  pass_rate_24h: number
  active_excursions: number
  excursions_this_week: number
  pending_reports: number
}

// ── Maintenance Types ───────────────────────────

export interface MaintenanceTaskEntry {
  id: string
  facility_id: string
  org_id: string
  title: string
  description: string | null
  category: string
  priority: string
  equipment_id: string | null
  compressor_id: string | null
  is_recurring: boolean
  recurrence_days: number | null
  recurrence_hours: number | null
  state: string
  due_date: string | null
  started_at: string | null
  completed_at: string | null
  assigned_to: string | null
  completion_notes: string | null
  parts_used: { part: string; qty: number }[] | null
  labor_hours: number | null
  checklist: { item: string; done: boolean }[] | null
  created_at: string
  updated_at: string
}

export interface MaintenanceDashboardStats {
  by_state: Record<string, number>
  overdue: number
  due_this_week: number
  completed_30d: number
}

// ── Escalation Types ────────────────────────────

export interface EscalationLevel {
  level: number
  delay_minutes: number
  notify: string[]
  label: string
}

export interface EscalationPolicyEntry {
  id: string
  org_id: string
  name: string
  description: string | null
  levels: EscalationLevel[]
  min_severity: string
  facility_ids: string[]
  is_active: boolean
  created_at: string
}

export interface EscalationEventEntry {
  id: string
  alert_id: string
  policy_id: string
  level: number
  notified_targets: string[]
  escalated_at: string
}

export const api = new ApiClient()

// ── Refrigerant Types ───────────────────────────

export interface RackTelemetry {
  rack_id: string
  rack_name: string
  suction_group: string | null
  total_kw: number | null
  active_compressors: number | null
  avg_suction_psi: number | null
  avg_discharge_psi: number | null
  design_suction_psi: number | null
  design_discharge_psi: number | null
}

export interface RefrigerantCircuit {
  id: string
  facility_id: string
  name: string
  refrigerant_type: string
  full_charge_lbs: number | null
  rack_id: string | null
  rack: RackTelemetry | null
  equipment_id: string | null
  zone_id: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LeakEvent {
  id: string
  facility_id: string
  circuit_id: string | null
  rack_name: string
  zone_name: string | null
  detection_method: string
  confidence: string
  status: string
  detected_at: string
  confirmed_at: string | null
  repaired_at: string | null
  closed_at: string | null
  estimated_loss_lbs: number | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface RefrigerantAdd {
  id: string
  facility_id: string
  circuit_id: string | null
  leak_event_id: string | null
  rack_name: string
  refrigerant_type: string
  amount_lbs: number
  cost_per_lb: number | null
  technician_name: string
  technician_epa_cert: string | null
  added_at: string
  notes: string | null
  created_at: string
}

export interface RepairRecord {
  id: string
  facility_id: string
  circuit_id: string | null
  leak_event_id: string | null
  rack_name: string
  description: string
  technician_name: string
  technician_company: string | null
  repaired_at: string
  parts_replaced: string | null
  verified_leak_free: boolean
  verification_method: string | null
  refrigerant_recovered_lbs: number | null
  notes: string | null
  callback_detected: boolean | null
  callback_detected_at: string | null
  callback_lbs_within_30d: number | null
  created_at: string
}

export interface RefrigerantDashboard {
  open_leak_events: number
  leak_events_30d: number
  refrigerant_added_30d_lbs: number
  repairs_30d: number
  sites_above_threshold: number
  per_facility: {
    facility_id: string
    name: string
    open_leaks: number
    adds_30d_lbs: number
    leak_rate_pct: number | null
  }[]
}

export interface AIMActCircuit {
  circuit_id: string | null
  circuit_name: string
  rack_name: string
  refrigerant_type: string
  full_charge_lbs: number | null
  total_added_lbs: number
  leak_rate_pct: number | null
  status: 'compliant' | 'warning' | 'exceeds_threshold' | 'no_charge_data'
  open_leak_events: number
  unrepaired_adds: number
}

export interface AIMActSummary {
  period_days: number
  circuits: AIMActCircuit[]
  facility_summary: {
    total_added_lbs: number
    avg_leak_rate_pct: number | null
    circuits_above_threshold: number
  }
}

export interface DetectionSettings {
  auto_detection: boolean
  forecasting: boolean
}

export interface CircuitForecast {
  circuit_id: string
  circuit_name: string | null
  org_id: string
  method: string
  projected_adds_lbs: number | null
  projected_adds_lbs_low: number | null
  projected_adds_lbs_high: number | null
  lbs_per_day: number | null
  days_to_aim_threshold: number | null
  days_to_aim_warning: number | null
  current_annual_leak_rate_pct: number | null
  confidence: 'low' | 'medium' | 'high' | null
  horizon_days: number
  computed_at: string
}

export interface DetectionInsights {
  auto_detected_events: number
  manual_events: number
  detection_breakdown: {
    pressure_trend: number
    refrigerant_add_pattern: number
    multi_signal: number
  }
  circuits_forecasted: number
  circuits_approaching_threshold: number
}

export interface Document {
  id: string
  org_id: string
  facility_id: string | null
  equipment_id: string | null
  document_type: string
  name: string
  storage_key: string
  content_type: string | null
  size_bytes: number | null
  metadata_: Record<string, unknown> | null
  uploaded_by: string | null
  created_at: string
}

export interface TunnelSession {
  id: string
  org_id: string
  facility_id: string
  agent_id: string | null
  user_id: string
  user_email: string
  target_device: string | null
  started_at: string
  ended_at: string | null
  end_reason: string | null
  ip_address: string | null
  notes: string | null
}

export interface MaintenanceEventEntry {
  id: string
  org_id: string
  facility_id: string
  equipment_id: string | null
  linked_alert_id: string | null
  linked_refrigerant_event_id: string | null
  event_type: string
  description: string
  technician_name: string
  technician_company: string | null
  occurred_at: string
  created_by: string | null
  created_at: string
}
