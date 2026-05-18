import { fetchEventSource } from '@microsoft/fetch-event-source'

type EventCallback = (data: any) => void

export class SseClient {
  private instanceId: number
  private getAuthToken: () => string
  private handlers: Map<string, EventCallback[]> = new Map()
  private abortController: AbortController | null = null

  constructor(instanceId: number, getAuthToken: () => string) {
    this.instanceId = instanceId
    this.getAuthToken = getAuthToken
  }

  on(event: string, callback: EventCallback) {
    const callbacks = this.handlers.get(event) || []
    callbacks.push(callback)
    this.handlers.set(event, callbacks)
  }

  async connect() {
    this.abortController = new AbortController()
    const url = `/api/v1/tasks/${this.instanceId}/events`

    try {
      await fetchEventSource(url, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${this.getAuthToken()}`,
        },
        signal: this.abortController.signal,
        onmessage: (event) => {
          const callbacks = this.handlers.get(event.event)
          if (callbacks) {
            try {
              const data = JSON.parse(event.data)
              callbacks.forEach((cb) => cb(data))
            } catch {
              // ignore parse errors
            }
          }
        },
        onerror: () => {
          this.abortController?.abort()
        },
      })
    } catch {
      // connection closed
    }
  }

  close() {
    this.abortController?.abort()
    this.handlers.clear()
  }
}
