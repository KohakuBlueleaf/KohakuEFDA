async function parse(response, url) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.error || `${url}: ${response.status}`)
  }
  return data
}

export async function getJson(url) {
  return parse(await fetch(url, { cache: "no-store" }), url)
}

export async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  })
  return parse(response, url)
}

export async function deleteJson(url) {
  return parse(await fetch(url, { method: "DELETE" }), url)
}

const RECONNECT_DELAY_MS = 1000

export function openEvents(runId, since, onEvent, onError) {
  // The stream reopens after the sequence number last seen, so nothing is replayed.
  let last = since
  let source = null
  let timer = null
  let closed = false
  function connect() {
    source = new EventSource(`api/runs/${runId}/events?since=${last}`)
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data)
        if (typeof event.seq === "number") {
          if (event.seq <= last) {
            return
          }
          last = event.seq
        }
        onEvent(event)
      } catch (error) {
        onError(error)
      }
    }
    source.onerror = (error) => {
      onError(error)
      source.close()
      if (!closed) {
        timer = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }
  }
  connect()
  return {
    close() {
      closed = true
      clearTimeout(timer)
      source?.close()
    },
  }
}
