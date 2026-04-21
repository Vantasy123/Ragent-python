export interface TablePageResult<T> {
  items: T[]
  total: number
  pageNo: number
  pageSize: number
}

export function unwrapData<T>(payload: any, fallback: T): T {
  if (payload === null || payload === undefined) {
    return fallback
  }
  return (payload.data ?? payload) as T
}

export function toArrayResult<T>(payload: any): T[] {
  const data = unwrapData<any>(payload, [])
  if (Array.isArray(data)) {
    return data
  }
  if (Array.isArray(data.items)) {
    return data.items
  }
  if (Array.isArray(data.records)) {
    return data.records
  }
  if (Array.isArray(data.list)) {
    return data.list
  }
  return []
}

export function toTablePageResult<T>(payload: any): TablePageResult<T> {
  const data = unwrapData<any>(payload, {})
  const items = Array.isArray(data)
    ? data
    : (data.items ?? data.records ?? data.list ?? [])

  return {
    items: Array.isArray(items) ? items : [],
    total: Number(data.total ?? data.count ?? items.length ?? 0),
    pageNo: Number(data.pageNo ?? data.page ?? 1),
    pageSize: Number(data.pageSize ?? data.size ?? (Array.isArray(items) ? items.length : 0)),
  }
}
