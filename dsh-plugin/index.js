/**
 * DSH status and voice approvals for Home Assistant.
 *
 * Two jobs, both scoped to "when the user is home":
 *
 * 1. Publish DeepSeek Harness status into Home Assistant as one REST state
 *    (`sensor.dsh_status` by default): bereit / arbeitet / wartet auf Freigabe,
 *    plus the last spoken answer and the number of open approvals.
 * 2. Answer DSH permission requests by voice: the living-room satellite asks
 *    "Soll ich das erlauben?", a spoken "Ja" grants once, "Nein" rejects, and
 *    anything else falls through to the other answerers (Telegram or browser).
 *
 * The module imports nothing on purpose: local bundles are linked into the
 * profile and must resolve without a package-manager step. Configuration lives
 * in the same JSON file as the voice bridge.
 */

/** Services this plugin needs before it can publish or ask. */
export const inject = ['tools', 'webServer']

/** Stable Cordis plugin name. */
export const name = 'dsh-status'

/** Version reported by `ha_approvals_status`. */
const VERSION = '1.1.0'

const DEFAULTS = {
  haUrl: 'http://192.168.0.155:8123',
  haToken: '',
  presence: [
    { entity_id: 'device_tracker.your_phone', homeStates: ['home'] },
    { entity_id: 'person.your_name', homeStates: ['home'] },
    { entity_id: 'binary_sensor.your_presence_sensor', homeStates: ['on'], weak: true },
  ],
  presenceMode: 'primary',
  announceEntity: 'assist_satellite.your_satellite',
  requireHome: true,
  publishStatus: true,
  statusEntity: 'sensor.dsh_status',
  statusIntervalSeconds: 30,
  voiceApproval: true,
  approvalTimeoutSeconds: 30,
}

const PRESENCE_CACHE_MS = 8000
const PUBLISH_MIN_GAP_MS = 1200

/** Words that grant one approval. */
const YES_WORDS = new Set([
  'ja', 'jawohl', 'jep', 'jup', 'jo', 'klar', 'ok', 'okay', 'erlaubt', 'genehmigt',
  'mach', 'machs', 'bitte', 'sicher', 'genau', 'richtig', 'passt', 'los', 'weiter',
  'einverstanden', 'freigabe', 'erlauben', 'ja bitte',
])

/** Words that reject an approval. */
const NO_WORDS = new Set([
  'nein', 'nee', 'nö', 'noe', 'nicht', 'stop', 'stopp', 'abbrechen', 'ablehnen',
  'lass', 'keinesfalls', 'niemals', 'verweigern', 'nein danke', 'auf keinen fall',
])

/** Normalize the raw row config. */
function normalizeConfig(raw) {
  const input = raw !== null && typeof raw === 'object' ? raw : {}
  return {
    configPath: typeof input.configPath === 'string' ? input.configPath : '',
    enabled: input.enabled === false ? false : true,
  }
}

/** Merge the settings file over the defaults. */
function normalizeSettings(raw) {
  const input = raw !== null && typeof raw === 'object' ? raw : {}
  const str = (key, fallback) => (typeof input[key] === 'string' && input[key].trim() !== '' ? input[key].trim() : fallback)
  const num = (key, fallback) => (typeof input[key] === 'number' && Number.isFinite(input[key]) && input[key] > 0 ? input[key] : fallback)
  const presence = Array.isArray(input.presence)
    ? input.presence
      .filter(entry => entry !== null && typeof entry === 'object' && typeof entry.entity_id === 'string' && entry.entity_id.includes('.'))
      .map(entry => ({
        entity_id: entry.entity_id,
        homeStates: Array.isArray(entry.homeStates) && entry.homeStates.length > 0
          ? entry.homeStates.map(value => String(value))
          : ['home'],
        weak: entry.weak === true,
      }))
    : DEFAULTS.presence.map(entry => ({ ...entry, homeStates: [...entry.homeStates] }))
  return {
    haUrl: str('haUrl', DEFAULTS.haUrl).replace(/\/+$/, ''),
    haToken: str('haToken', DEFAULTS.haToken),
    bridgeToken: str('bridgeToken', ''),
    presence,
    presenceMode: input.presenceMode === 'any' ? 'any' : 'primary',
    announceEntity: str('announceEntity', DEFAULTS.announceEntity),
    requireHome: input.requireHome === false ? false : DEFAULTS.requireHome,
    publishStatus: input.publishStatus === false ? false : DEFAULTS.publishStatus,
    statusEntity: str('statusEntity', DEFAULTS.statusEntity),
    statusIntervalSeconds: Math.max(10, Math.min(Math.round(num('statusIntervalSeconds', DEFAULTS.statusIntervalSeconds)), 600)),
    voiceApproval: input.voiceApproval === false ? false : DEFAULTS.voiceApproval,
    approvalTimeoutSeconds: Math.max(8, Math.min(Math.round(num('approvalTimeoutSeconds', DEFAULTS.approvalTimeoutSeconds)), 120)),
  }
}

/** Read the settings file, cached by modification time. */
function readSettings(ctx, cfg, cache) {
  if (cfg.configPath === '') return normalizeSettings({})
  const fs = globalThis.process?.getBuiltinModule?.('node:fs')
  if (fs === undefined) return normalizeSettings(cache.value ?? {})
  let stat
  try {
    stat = fs.statSync(cfg.configPath)
  } catch {
    stat = null
  }
  if (stat === null) return normalizeSettings(cache.value ?? {})
  const stamp = `${stat.mtimeMs}:${stat.size}`
  if (cache.stamp === stamp && cache.value !== undefined) return cache.value
  try {
    cache.value = normalizeSettings(JSON.parse(fs.readFileSync(cfg.configPath, 'utf8')))
    cache.stamp = stamp
    return cache.value
  } catch (error) {
    ctx.logger?.('dsh-status')?.warn?.(`settings file unreadable: ${error instanceof Error ? error.message : String(error)}`)
    return normalizeSettings(cache.value ?? {})
  }
}

/** Pull the first plain speech string out of a service response. */
function speechOf(response) {
  const candidates = [
    response?.response?.speech?.plain?.speech,
    response?.speech?.plain?.speech,
    response?.response?.speech,
    response?.speech,
  ]
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim() !== '') return candidate.trim()
  }
  return ''
}

/** Decide Ja, Nein, or nothing from a spoken answer. */
function interpretAnswer(text) {
  const normalized = String(text ?? '')
    .toLowerCase()
    .replace(/[.,!?;:()[\]{}"]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (normalized === '') return undefined
  if (normalized.includes('auf keinen fall') || normalized.includes('nein danke')) return 'rejected'
  const words = normalized.split(' ')
  for (const word of words) {
    if (NO_WORDS.has(word)) return 'rejected'
  }
  for (const word of words) {
    if (YES_WORDS.has(word)) return 'allowed-once'
  }
  return undefined
}

/** Shorten a sentence for a spoken question. */
function clip(text, limit) {
  const value = String(text ?? '').replace(/\s+/g, ' ').trim()
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`
}

export function apply(ctx, rawConfig) {
  const cfg = normalizeConfig(rawConfig)
  if (!cfg.enabled) return
  const logger = ctx.logger?.('dsh-status')
  const settingsCache = { stamp: undefined, value: undefined }
  const presenceCache = { at: 0, value: undefined }
  const settings = () => readSettings(ctx, cfg, settingsCache)

  const status = { value: 'bereit', detail: '', session: '', pending: 0, updatedAt: new Date().toISOString() }
  let lastPublishAt = 0
  let publishDeferred = false
  let askInFlight = false

  /** One authenticated HA call. */
  async function haFetch(path, { method = 'GET', body, timeoutMs = 15000 } = {}) {
    const conf = settings()
    if (conf.haToken === '') throw new Error('kein Home-Assistant-Token konfiguriert')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetch(conf.haUrl + path, {
        method,
        headers: { authorization: `Bearer ${conf.haToken}`, 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })
      const text = await response.text()
      let parsed
      try {
        parsed = text === '' ? undefined : JSON.parse(text)
      } catch {
        parsed = text
      }
      if (!response.ok) throw new Error(`Home Assistant ${method} ${path} -> HTTP ${response.status}: ${String(typeof parsed === 'string' ? parsed : JSON.stringify(parsed)).slice(0, 200)}`)
      return parsed
    } finally {
      clearTimeout(timer)
    }
  }

  /** Call one HA service and unwrap a service response. */
  async function callService(domain, service, data) {
    const result = await haFetch(`/api/services/${encodeURIComponent(domain)}/${encodeURIComponent(service)}`, { method: 'POST', body: data ?? {}, timeoutMs: 45000 })
    if (result !== null && typeof result === 'object' && !Array.isArray(result) && result.service_response !== undefined) return result.service_response
    return result
  }

  /** Presence check over the configured sources. */
  async function presence(force = false) {
    const conf = settings()
    if (!force && presenceCache.value !== undefined && Date.now() - presenceCache.at < PRESENCE_CACHE_MS) return presenceCache.value
    let home = false
    let decided = false
    let weakHome = false
    const sources = []
    for (const entry of conf.presence) {
      let value = null
      let error
      try {
        const state = await haFetch(`/api/states/${encodeURIComponent(entry.entity_id)}`, { timeoutMs: 8000 })
        value = state?.state === undefined ? null : String(state.state)
      } catch (caught) {
        error = caught instanceof Error ? caught.message : String(caught)
      }
      const usable = value !== null && value !== 'unavailable' && value !== 'unknown' && value !== 'none'
      const isHome = usable ? entry.homeStates.includes(value) : false
      sources.push({ entity_id: entry.entity_id, state: value, home: isHome, weak: entry.weak === true, error })
      if (!usable) continue
      if (conf.presenceMode === 'any') {
        if (isHome) { home = true; decided = true }
        continue
      }
      if (entry.weak === true) { if (isHome) weakHome = true; continue }
      if (!decided) { home = isHome; decided = true }
    }
    if (conf.presenceMode !== 'any' && !decided && weakHome) { home = true; decided = true }
    const answer = { home, decided, mode: conf.presenceMode, sources }
    presenceCache.value = answer
    presenceCache.at = Date.now()
    return answer
  }

  /** Push the current status into Home Assistant. */
  async function publishStatus(reason = 'update') {
    const conf = settings()
    if (conf.publishStatus !== true) return
    const now = Date.now()
    if (now - lastPublishAt < PUBLISH_MIN_GAP_MS) {
      if (!publishDeferred) {
        publishDeferred = true
        setTimeout(() => { publishDeferred = false; void publishStatus('deferred') }, PUBLISH_MIN_GAP_MS + 80)
      }
      return
    }
    lastPublishAt = now
    status.updatedAt = new Date().toISOString()
    try {
      await haFetch(`/api/states/${encodeURIComponent(conf.statusEntity)}`, {
        method: 'POST',
        timeoutMs: 10000,
        body: {
          state: status.value,
          attributes: {
            friendly_name: 'DeepSeek Harness',
            icon: 'mdi:robot-happy-outline',
            detail: status.detail,
            session: status.session,
            open_approvals: status.pending,
            updated_at: status.updatedAt,
            version: VERSION,
            reason,
          },
        },
      })
    } catch (error) {
      logger?.warn?.(`status publish failed: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  /** Ask one question on the satellite and return the spoken answer text. */
  async function askSatellite(question, timeoutMs) {
    const conf = settings()
    if (conf.announceEntity === '') return ''
    const call = callService('assist_satellite', 'ask_question', { entity_id: conf.announceEntity, question })
      .then(response => speechOf(response))
      .catch((error) => {
        logger?.warn?.(`ask_question failed: ${error instanceof Error ? error.message : String(error)}`)
        return ''
      })
    const timeout = new Promise(resolve => { const timer = setTimeout(() => resolve(''), timeoutMs); if (typeof timer.unref === 'function') timer.unref() })
    return await Promise.race([call, timeout])
  }

  /** Voice answerer for one approval request; undefined delegates to the next answerer. */
  async function askByVoice(request) {
    const conf = settings()
    let currentPresence
    try {
      currentPresence = await presence()
    } catch (error) {
      logger?.warn?.(`presence check failed: ${error instanceof Error ? error.message : String(error)}`)
      return undefined
    }
    if (conf.requireHome && currentPresence.home !== true) return undefined
    const reason = request?.displayReason?.de ?? request?.displayReason?.en ?? request?.reason ?? ''
    const what = reason !== '' ? clip(reason, 180) : `das Werkzeug ${request?.toolName ?? 'unbekannt'} ausführen`
    const question = `DeepSeek Harness fragt: ${what}. Soll ich das erlauben? Sag Ja oder Nein.`
    if (askInFlight) return undefined
    askInFlight = true
    try {
      const answer = await askSatellite(question, conf.approvalTimeoutSeconds * 1000)
      if (answer === '') return undefined
      const verdict = interpretAnswer(answer)
      logger?.info?.(`voice approval: "${answer}" -> ${verdict ?? 'unknown'}`)
      if (verdict === undefined) {
        const retry = await askSatellite('Bitte sag nur Ja oder Nein.', Math.min(conf.approvalTimeoutSeconds, 15) * 1000)
        const second = interpretAnswer(retry)
        if (second !== undefined) return second
        return undefined
      }
      return verdict
    } finally {
      askInFlight = false
    }
  }

  /** Serve the status snapshot the Home Assistant integration polls. */
  async function handleStatusRoute(req, res) {
    const conf = settings()
    if (req.method !== 'GET') {
      res.writeHead(405, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: 'method not allowed' }))
      return
    }
    const authorization = typeof req.headers.authorization === 'string' ? req.headers.authorization : ''
    const presented = authorization.toLowerCase().startsWith('bearer ') ? authorization.slice(7).trim() : ''
    if (conf.bridgeToken === '' || presented !== conf.bridgeToken) {
      res.writeHead(401, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: 'invalid bridge token' }))
      return
    }
    let answer
    try {
      answer = await presence()
    } catch (error) {
      answer = { home: null, decided: false, mode: conf.presenceMode, sources: [], error: error instanceof Error ? error.message : String(error) }
    }
    const payload = JSON.stringify({
      ok: true,
      version: VERSION,
      updated_at: new Date().toISOString(),
      status: {
        state: status.value,
        detail: status.detail,
        session: status.session,
        pending: status.pending,
        updated_at: status.updatedAt,
      },
      presence: {
        home: answer.home === true,
        known: answer.home !== null && answer.home !== undefined,
        mode: answer.mode,
        sources: answer.sources.map(entry => ({ entity_id: entry.entity_id, state: entry.state, home: entry.home })),
      },
      approvals: {
        voice: conf.voiceApproval,
        requireHome: conf.requireHome,
        timeoutSeconds: conf.approvalTimeoutSeconds,
      },
      announce_entity: conf.announceEntity,
      ha_url: conf.haUrl,
    })
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
    res.end(payload)
  }

  ctx.effect(() => {
    // Status follows live session activity.
    const offSession = ctx.on('session/event', (session, event) => {
      if (event.type === 'turn/start') {
        status.value = 'arbeitet'
        status.session = String(session?.id ?? '').slice(0, 8)
        void publishStatus('turn-start')
        return
      }
      if (event.type === 'assistant/message') {
        const content = event.data?.message?.content
        if (Array.isArray(content)) {
          const text = content.filter(block => block?.type === 'text' && typeof block.text === 'string').map(block => block.text).join('')
          if (text !== '') status.detail = clip(text, 220)
        }
        return
      }
      if (event.type === 'turn/end') {
        status.value = status.pending > 0 ? 'wartet auf Freigabe' : 'bereit'
        void publishStatus('turn-end')
      }
    })

    // Voice answerer: prepended so it runs before Telegram and the browser prompt.
    const offApproval = ctx.on('approval/request', async (request, next) => {
      status.pending += 1
      status.value = 'wartet auf Freigabe'
      void publishStatus('approval-asked')
      try {
        const conf = settings()
        if (conf.voiceApproval !== true) return await next()
        const verdict = await askByVoice(request)
        if (verdict !== undefined) return verdict
        return await next()
      } finally {
        status.pending = Math.max(0, status.pending - 1)
        status.value = status.pending > 0 ? 'wartet auf Freigabe' : 'bereit'
        void publishStatus('approval-done')
      }
    }, { prepend: true })

    const offStatusRoute = ctx.webServer?.register?.({ kind: 'exact', path: '/api/ha-voice/status', handler: handleStatusRoute })
    const offStatusRouteSlash = ctx.webServer?.register?.({ kind: 'exact', path: '/api/ha-voice/status/', handler: handleStatusRoute })

    ctx.tools.register({
      name: 'ha_approvals_status',
      description: 'Report whether DSH publishes its status to Home Assistant and whether approvals can be answered by voice right now.',
      parameters: { type: 'object', additionalProperties: false, properties: {} },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            statusEntity: { type: 'string' },
            publishStatus: { type: 'boolean' },
            voiceApproval: { type: 'boolean' },
            requireHome: { type: 'boolean' },
            currentStatus: { type: 'string' },
            openApprovals: { type: 'integer' },
            detail: { type: 'string' },
            updatedAt: { type: 'string' },
            version: { type: 'string' },
          },
          required: ['statusEntity', 'currentStatus'],
        },
        render: (_args, value) => [{
          type: 'text',
          text: `Status ${value.currentStatus} auf ${value.statusEntity} (${value.openApprovals} offene Freigaben, Sprachfreigabe ${value.voiceApproval ? 'an' : 'aus'})`,
        }],
      },
      async execute() {
        const conf = settings()
        return {
          statusEntity: conf.statusEntity,
          publishStatus: conf.publishStatus,
          voiceApproval: conf.voiceApproval,
          requireHome: conf.requireHome,
          currentStatus: status.value,
          openApprovals: status.pending,
          detail: status.detail,
          updatedAt: status.updatedAt,
          version: VERSION,
        }
      },
    })

    ctx.tools.register({
      name: 'ha_status_publish',
      description: 'Publish the current DeepSeek Harness status to Home Assistant immediately, for example after a long step so the dashboard is fresh.',
      parameters: { type: 'object', additionalProperties: false, properties: {} },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: { ok: { type: 'boolean' }, statusEntity: { type: 'string' }, state: { type: 'string' } },
          required: ['ok'],
        },
        render: (_args, value) => [{ type: 'text', text: value.ok ? `${value.statusEntity} = ${value.state}` : 'Status konnte nicht veröffentlicht werden' }],
      },
      async execute() {
        const conf = settings()
        try {
          await publishStatus('tool')
          return { ok: true, statusEntity: conf.statusEntity, state: status.value }
        } catch (error) {
          return { ok: false, statusEntity: conf.statusEntity, state: error instanceof Error ? error.message : String(error) }
        }
      },
    })

    const heartbeat = setInterval(() => { void publishStatus('heartbeat') }, settings().statusIntervalSeconds * 1000)
    if (typeof heartbeat.unref === 'function') heartbeat.unref()
    void publishStatus('startup')

    logger?.info?.(`DSH status and voice approvals active (${settings().statusEntity})`)

    return () => {
      clearInterval(heartbeat)
      offSession()
      offApproval()
      offStatusRoute?.()
      offStatusRouteSlash?.()
    }
  })
}
