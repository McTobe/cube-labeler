// A small shared store: components read it with useStore() and redraw when it changes.
import { useEffect, useState } from 'preact/hooks';

export function createStore(initial) {
  let state = initial;
  const listeners = new Set();
  return {
    get: () => state,
    set(change) {
      const next = typeof change === 'function' ? change(state) : change;
      state = { ...state, ...next };
      listeners.forEach((listener) => listener(state));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export function useStore(store) {
  const [, redraw] = useState(0);
  useEffect(() => store.subscribe(() => redraw((n) => n + 1)), [store]);
  return store.get();
}
