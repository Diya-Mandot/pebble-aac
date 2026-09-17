// Structured output of continuous voice capture (Track A). Track B (conversation buffer /
// context formalization) subscribes to this instead of coupling directly to the recognition
// internals in App.tsx -- lets Track B be built against a stub emitter with the same shape.
export type Turn = {
  text: string
  timestamp: number
}

type TurnListener = (turn: Turn) => void

const listeners = new Set<TurnListener>()

export function onTurn(listener: TurnListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function emitTurn(turn: Turn): void {
  listeners.forEach((listener) => listener(turn))
}
