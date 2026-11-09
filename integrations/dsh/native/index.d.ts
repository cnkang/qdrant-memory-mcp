import '@deepseek-ai/dsh-llm'

declare module '@deepseek-ai/dsh-llm' {
  interface LlmRequestPurposeMap {
    'qdrant-memory-extraction': {}
  }
  interface MessageSourceMap {
    'qdrant-memory': {
      kind: 'qdrant-memory'
      memoryIds: readonly string[]
      queryHash: string
    }
  }
}

export declare const name: string
export declare const inject: readonly string[]
export declare const CANDIDATE_SCHEMA: 'qdrant-memory/extraction-v1'
export declare const SUPPORTED_DSH_RELEASE: '0.2.2-rc.1'
export declare const RECOVERY_PROGRESS_RECORD: 'plugin:qdrant-memory/recovery-progress'
export type NativeConfig = {
  auto_recall: Readonly<{
    enabled: boolean
    timeout_ms: number
    top_k: number
    min_score?: number
    dedupe: boolean
    cache: boolean
    cache_ttl_ms: number
  }>
  auto_capture: Readonly<{
    enabled: boolean
    timeout_ms: number
    max_input_chars: number
    max_candidates: number
    max_output_tokens: number
  }>
  memory_injection: Readonly<{
    enabled: boolean
    max_chars: number
    include_source_metadata: boolean
  }>
}
export declare const DEFAULT_CONFIG: Readonly<NativeConfig>
export declare const Config: unknown
declare module '@deepseek-ai/dsh-session' {
  interface PluginRecordMap {
    'plugin:qdrant-memory/capture-state': {
      session_id: string
      enabled: boolean
      after_seq: number
    }
  }
}
export declare function runtimeTarget(env: Record<string, string | undefined>): {
  python: string
  endpoint: string
  token: string
  caFile?: string
}
export declare function parseCandidates(output: string, maxCandidates?: number, userText?: string): {
  candidates: Array<{
    text: string
    category: string[]
    importance: number
    replacement_intent: boolean
  }>
  replacement_context: string
}
export declare function compileTurn(events: unknown[], sessionId: string, turn: number, maxChars?: number): {
  event_id: string
  session_id: string
  user: string
  assistant: string
  provider?: string
  model?: string
} | null
export declare function formatMemories(result: unknown, maxChars?: number, options?: {
  topK?: number
  minScore?: number
  dedupe?: boolean
  includeSourceMetadata?: boolean
}): { text: string; ids: string[]; chars: number }
export declare function runRuntimeRequest(mode: 'remote-call' | 'remote-event', payload: unknown, options?: {
  signal?: AbortSignal
  timeoutMs?: number
  action?: 'submit' | 'status' | 'retry' | 'cancel'
  spawnProcess?: typeof import('node:child_process').spawn
}): Promise<Record<string, unknown>>
export type NativeMetrics = {
  recall_requests: number
  recall_owner_calls: number
  recall_hits: number
  recall_failures: number
  recall_cancelled: number
  recall_cache_hits: number
  recall_latency_ms_total: number
  recall_latency_ms_count: number
  injected_memory_count: number
  injected_context_chars: number
  capture_turns_seen: number
  capture_turns_eligible: number
  capture_events_committed: number
  capture_failed: number
  capture_backlog: number
  capture_recovery_count: number
}
export declare function apply(
  ctx: unknown,
  config: NativeConfig,
  runtimeRequest?: typeof runRuntimeRequest,
): (() => void) & { metrics: () => NativeMetrics }
