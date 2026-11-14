import type { SSEEvent, SSEEventType } from './types'

function parseBlock(block: string): SSEEvent | null {
  let type = ''
  const dataLines: string[] = []

  for (const rawLine of block.split(/\r?\n/)) {
    if (rawLine.startsWith('event:')) type = rawLine.slice(6).trim()
    if (rawLine.startsWith('data:')) dataLines.push(rawLine.slice(5).trimStart())
  }

  if (!type || dataLines.length === 0) return null
  return {
    type: type as SSEEventType,
    data: JSON.parse(dataLines.join('\n')) as Record<string, unknown>,
  }
}

export async function* parseSSEStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<SSEEvent> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''

      for (const block of blocks) {
        const event = parseBlock(block)
        if (event) yield event
      }
      if (done) break
    }

    if (buffer.trim()) {
      const event = parseBlock(buffer)
      if (event) yield event
    }
  } finally {
    reader.releaseLock()
  }
}
