declare module "tweetnacl" {
  export type BoxKeyPair = {
    publicKey: Uint8Array;
    secretKey: Uint8Array;
  };

  export type SignKeyPair = {
    publicKey: Uint8Array;
    secretKey: Uint8Array;
  };

  type BoxFn = {
    (
      data: Uint8Array,
      nonce: Uint8Array,
      publicKey: Uint8Array,
      secretKey: Uint8Array,
    ): Uint8Array;
    open(
      data: Uint8Array,
      nonce: Uint8Array,
      publicKey: Uint8Array,
      secretKey: Uint8Array,
    ): Uint8Array | null;
    before(
      publicKey: Uint8Array,
      secretKey: Uint8Array,
    ): Uint8Array;
    after(
      data: Uint8Array,
      nonce: Uint8Array,
      key: Uint8Array,
    ): Uint8Array;
    keyPair(): BoxKeyPair;
  };

  type DetachedFn = {
    (data: Uint8Array, secretKey: Uint8Array): Uint8Array;
    verify(
      data: Uint8Array,
      signature: Uint8Array,
      publicKey: Uint8Array,
    ): boolean;
  };

  const nacl: {
    randomBytes(length: number): Uint8Array;
    box: BoxFn;
    sign: {
      keyPair(): SignKeyPair;
      detached: DetachedFn;
    };
  };

  export default nacl;
}
