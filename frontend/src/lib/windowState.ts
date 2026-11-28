/** View state belongs to one browsing context. Disk snapshots remain owner-scoped. */
const memory = new Map<string, string>();
export function windowStateStorage(): Pick<Storage, "getItem" | "setItem" | "removeItem"> {
  try {
    const storage = window.sessionStorage;
    // Some WebViews expose the object but reject every operation.
    storage.getItem("efhc:storage-check");
    return storage;
  } catch {
    return {getItem: key => memory.get(key) ?? null, setItem: (key, value) => {memory.set(key, value);}, removeItem: key => {memory.delete(key);}};
  }
}
