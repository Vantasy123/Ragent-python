export interface IngestionModuleOption {
  key: string
  label: string
  description: string
  category: string
}

export interface IngestionPipelinePreset {
  id: string
  label: string
  description: string
  modules: string[]
}

export interface IngestionModuleSelection {
  key: string
}

export const ingestionModuleCatalog: IngestionModuleOption[] = [
  { key: 'fetcher', label: '文件抓取', description: '读取本地上传文件或远端资源。', category: '输入' },
  { key: 'parser', label: '内容解析', description: '把 PDF、Word、Markdown 等文件转成文本。', category: '处理' },
  { key: 'chunker', label: '文本切片', description: '按 chunk 策略把长文本拆成可检索片段。', category: '处理' },
  { key: 'indexer', label: '向量索引', description: '将片段写入 PGVector，供聊天检索使用。', category: '输出' },
]

export const ingestionPipelinePresets: IngestionPipelinePreset[] = [
  {
    id: 'standard_rag',
    label: '标准 RAG 入库',
    description: '最常用的文档摄取链路，包含抓取、解析、切片和索引。',
    modules: ['fetcher', 'parser', 'chunker', 'indexer'],
  },
  {
    id: 'parse_only',
    label: '解析预检',
    description: '先验证文件读取与解析结果，适合定位文档内容异常。',
    modules: ['fetcher', 'parser'],
  },
  {
    id: 'chunk_debug',
    label: '切片调试',
    description: '用于验证 chunk 规模和顺序，适合调 chunk 参数。',
    modules: ['fetcher', 'parser', 'chunker'],
  },
]

export function normalizePipelineNodes(nodes: unknown): IngestionModuleSelection[] {
  if (!Array.isArray(nodes)) return []
  return nodes
    .map((item) => {
      if (typeof item === 'string') return { key: item }
      if (item && typeof item === 'object') {
        const node = item as Record<string, unknown>
        const rawKey = node.name ?? node.type ?? node.key
        if (typeof rawKey === 'string' && rawKey.trim()) {
          return { key: rawKey.trim() }
        }
      }
      return null
    })
    .filter((item): item is IngestionModuleSelection => !!item)
}

export function buildPipelineNodes(modules: IngestionModuleSelection[]) {
  return modules.map((item) => ({ name: item.key }))
}

export function moduleMeta(key: string) {
  return ingestionModuleCatalog.find((item) => item.key === key)
}
