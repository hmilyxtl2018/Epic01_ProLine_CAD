import "@testing-library/jest-dom/vitest";

// Node 22+ ships a built-in `localStorage` that requires a `--localstorage-file`
// path; it shadows jsdom's localStorage. We replace it with an in-memory shim
// so tests that read/write storage just work.
class MemStorage implements Storage {
  private map = new Map<string, string>();
  get length() { return this.map.size; }
  clear() { this.map.clear(); }
  getItem(k: string) { return this.map.has(k) ? this.map.get(k)! : null; }
  setItem(k: string, v: string) { this.map.set(k, String(v)); }
  removeItem(k: string) { this.map.delete(k); }
  key(i: number) { return Array.from(this.map.keys())[i] ?? null; }
}

const _ls = new MemStorage();
const _ss = new MemStorage();
Object.defineProperty(globalThis, "localStorage", { value: _ls, configurable: true, writable: true });
Object.defineProperty(globalThis, "sessionStorage", { value: _ss, configurable: true, writable: true });
if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", { value: _ls, configurable: true, writable: true });
  Object.defineProperty(window, "sessionStorage", { value: _ss, configurable: true, writable: true });
}
