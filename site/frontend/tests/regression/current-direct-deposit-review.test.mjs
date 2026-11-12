import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const file = (name) => readFileSync(new URL(name, import.meta.url), "utf8");
const source = file("../../src/lib/ton/direct-deposit-review.ts");
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const mod = { exports: {} };
new Function("module", "exports", js)(mod, mod.exports);
const { formatNanoTon, createDirectDepositReview } = mod.exports;

const metadata = {
  purpose: "direct_efhc_jetton_deposit",
  asset: "EFHC",
  receiver_owner_address: "project-recipient-address",
  jetton_master_address: "verified-efhc-master",
  jetton_decimals: 8,
  forward_payload_text: "EFHC:GID:0000003101",
  fee_message_ton_amount: "50000000",
  forward_ton_amount: "1000000",
  memo_binding: "global_id",
};
const tx = {
  validUntil: 1_800_000_000,
  network: "-239",
  messages: [{ address: "sender-jetton-wallet-contract", amount: "50000000", payload: "real-TEP74-BOC" }],
};
const prepare = (options = {}) => createDirectDepositReview({
  tx,
  metadata,
  walletAddress: "owner-wallet",
  amountEfhc: "1.00000000",
  ...options,
});

test("TON attachment and forwarded amount use exact integer nanoTON, never float", () => {
  for (const [nano, expected] of [
    ["0", "0"], ["1", "0.000000001"], ["50000000", "0.05"],
    ["1000000000", "1"], ["1234567890", "1.23456789"],
    ["123456789012345678901234567890", "123456789012345678901.23456789"],
  ]) assert.equal(formatNanoTon(nano), expected);
  for (const invalid of ["-1", "0.01", "1e8", "", " 1", "NaN"]) {
    assert.throws(() => formatNanoTon(invalid), /INVALID_TON_ATTACHMENT/);
  }
});

test("review shows actual EFHC, project recipient and Jetton contract distinctly", () => {
  const result = prepare();
  assert.equal(result.amountEfhc, "1.00000000");
  assert.equal(result.receiverAddress, metadata.receiver_owner_address);
  assert.equal(result.executionContractAddress, tx.messages[0].address);
  assert.notEqual(result.receiverAddress, result.executionContractAddress);
  assert.equal(result.jettonMasterAddress, metadata.jetton_master_address);
  assert.equal(result.memo, "EFHC:GID:0000003101");
  assert.equal(result.attachedTon, "0.05");
  assert.equal(result.forwardedTon, "0.001");
  assert.equal(result.network, "TON Mainnet");
  assert.equal(result.expiresAt, tx.validUntil);
  assert.equal("actualNetworkFeeTon" in result, false,
    "review must never invent a confirmed gas fee");
});

test("review cannot show mismatched wallet request or invalid on-chain metadata", () => {
  assert.throws(() => prepare({
    tx: { ...tx, messages: [{ ...tx.messages[0], amount: "40000000" }] },
  }), /DIRECT_DEPOSIT_REVIEW_INVALID/);
  assert.throws(() => prepare({
    metadata: { ...metadata, forward_ton_amount: "60000000" },
  }), /DIRECT_DEPOSIT_REVIEW_INVALID/);
  assert.throws(() => prepare({
    metadata: { ...metadata, forward_payload_text: "wrong-owner" },
  }), /DIRECT_DEPOSIT_REVIEW_INVALID/);
  assert.throws(() => prepare({
    tx: { ...tx, network: "-888" },
  }), /DIRECT_DEPOSIT_REVIEW_INVALID/);
  assert.throws(() => prepare({
    tx: { ...tx, messages: [] },
  }), /DIRECT_DEPOSIT_REVIEW_INVALID/);
});

test("review remains in app until explicit wallet click; it does not auto-send", () => {
  const component = file("../../src/components/DepositModal.tsx");
  const originalSend = component.indexOf("const sendPreparedDirectDeposit = useCallback(");
  const reviewMarkup = component.indexOf('data-direct-deposit-review="ready"');
  const action = component.indexOf('data-direct-deposit-action="send-efhc-jetton"');
  assert.ok(originalSend >= 0 && reviewMarkup > originalSend && action > reviewMarkup);
  assert.match(component, /const review = createDirectDepositReview\(/);
  assert.match(component, /setPreparedDeposit\(\{\s*tx,\s*review,/);
  assert.match(component, /preparedDeposit\s*\?\s*t\("deposit\.review_confirm"\)/);
  assert.match(component, /disabled=\{Boolean\(preparedDeposit\) \|\| transactionPhase === "signing"\}/);
  assert.match(component, /data-direct-deposit-review-attached="ton"/);
  assert.match(component, /data-direct-deposit-review-fee="pending"/);
  assert.match(component, /data-direct-deposit-review-recipient="owner"/);
  assert.match(component, /data-direct-deposit-action="edit-amount"/);
  assert.match(component, /void sendTransaction\(ready\.tx\)\.then\(/);
  assert.doesNotMatch(component.slice(originalSend, component.indexOf("async function sendDirectEfhcDeposit",originalSend)),
    /await (?:openDeposit|buildEfhcDirectDepositTx|sendTransaction)/);
});

test("official wallet confirmation portal stays interactive during EFHC modal background inert", () => {
  const modal = file("../../src/components/ui/Modal.tsx");
  assert.match(modal, /child\.id !== "tc-widget-root"/);
  assert.match(modal, /walletRoot\.contains\(document\.activeElement\)/);
  assert.match(modal, /data-tc-actions-modal-container/);
  assert.match(modal, /element\.setAttribute\("inert", ""\)/);
  assert.match(modal, /modalBackgroundInertSnapshots\.delete\(element\)/);
  const provider = file("../../src/lib/wallet-provider/WalletProvider.tsx");
  assert.match(provider, /OfficialTonConnectProvider/);
  assert.match(provider, /modals:\s*"all"/);
});

test("all supported languages show a non-empty review and explicit fee caveat", () => {
  const langs = ["en","ru","uk","de","fr","es","it","tr","pl","da","hi","id","sw","pt","ko","ja"];
  const keys = ["title","send","receive","recipient","ton_attached",
    "network_fee","fee_pending","fee_explanation","details","network",
    "sender","execution","master","forward_ton","memo","valid_until",
    "confirm","edit"];
  for (const lang of langs) {
    const dict = JSON.parse(file("../../public/locale/" + lang + ".json"));
    for (const suffix of keys) {
      const key = "deposit.review_" + suffix;
      assert.ok(typeof dict[key] === "string" && dict[key].trim().length > 0,
        "missing review locale " + lang + " " + key);
    }
  }
});
