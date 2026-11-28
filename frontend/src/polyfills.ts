import { Buffer } from 'buffer';

declare global {
  interface Window {
    Buffer?: typeof Buffer;
    global?: Window & typeof globalThis;
  }
}

if (typeof window !== 'undefined') {
  window.Buffer = window.Buffer || Buffer;
  window.global = window.global || window;
}
