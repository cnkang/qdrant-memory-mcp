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
export type NativeConfig = {
  auto_recall: {
    enabled: boolean
    timeout_ms: number
    top_k: number
    min_score?: number
    dedupe: boolean
    cache: boolean
    cache_ttl_ms: number
  }
  auto_capture: Readonly<{
    enabled: boolean
    timeout_ms: number
    max_input_chars: number
    max_candidates: number
    max_output_tokens: number
  }>
  memory_injection: {
    enabled: boolean
    max_chars: number
    include_source_metadata: boolean
  }
}
export declare const DEFAULT_CONFIG: Readonly<NativeConfig>
export declare const Config: unknown
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
}): { text: string; ids: string[] }
export declare function runRuntimeRequest(mode: 'remote-call' | 'remote-event', payload: unknown, options?: {
  signal?: AbortSignal
  timeoutMs?: number
  action?: 'submit' | 'status' | 'cancel'
}): Promise<Record<string, unknown>>
export declare function apply(
  ctx: unknown,
  config: NativeConfig,
  runtimeRequest?: typeof runRuntimeRequest,
): () => void
