declare module 'tweetnacl-util' {
  const util: {
    encodeBase64(value: Uint8Array): string;
    decodeBase64(value: string): Uint8Array;
    encodeUTF8(value: Uint8Array): string;
    decodeUTF8(value: string): Uint8Array;
  };
  export default util;
}
