import { describe, expect, it } from 'vitest'
import { parseSSEStream } from './sse'

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

describe('parseSSEStream', () => {
  it('parses events split across transport chunks', async () => {
    const stream = streamFrom([
      'event: meta\ndata: {"session_id":"session_1"}\n',
      '\nevent: token\ndata: {"text":"七',
      '天内","tier":1}\n\nevent: done\ndata: {"status":"complete","tier":1}\n\n',
    ])

    const events = []
    for await (const event of parseSSEStream(stream)) events.push(event)

    expect(events).toEqual([
      { type: 'meta', data: { session_id: 'session_1' } },
      { type: 'token', data: { text: '七天内', tier: 1 } },
      { type: 'done', data: { status: 'complete', tier: 1 } },
    ])
  })

  it('parses a final event without a trailing blank line', async () => {
    const events = []
    for await (const event of parseSSEStream(streamFrom(['event: error\ndata: {"code":"offline"}']))) {
      events.push(event)
    }

    expect(events).toEqual([{ type: 'error', data: { code: 'offline' } }])
  })
})
