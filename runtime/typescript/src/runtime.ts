export type RadiusProvider = "local" | "para";

export interface RadiusWalletRuntime {
  walletAddress(input?: { provider?: RadiusProvider }): Promise<Record<string, unknown>>;
  balance(input?: { provider?: RadiusProvider; address?: string }): Promise<Record<string, unknown>>;
  sendSbc(input: { provider?: RadiusProvider; to: string; amount_sbc: string }): Promise<Record<string, unknown>>;
  sendRusd(input: { provider?: RadiusProvider; to: string; amount_rusd: string }): Promise<Record<string, unknown>>;
  txStatus(input: { tx_hash: string }): Promise<Record<string, unknown>>;
  chainInfo(): Promise<Record<string, unknown>>;
}

export const radiusToolNames = [
  "radius_wallet_address",
  "radius_balance",
  "radius_send_sbc",
  "radius_send_rusd",
  "radius_tx_status",
  "radius_chain_info",
] as const;

