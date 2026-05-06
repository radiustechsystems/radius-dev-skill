# Legacy x402 CLI Access with curl + cast

Prefer `radius-cli wallet x402 <verb> <url>` for one-shot terminal and agent
access to x402-gated endpoints. This reference is a legacy/specialized fallback
for environments that cannot use `radius-cli` and already have a funded Foundry
keystore account.

For fresh agent-created wallets, do not use this cast flow. Use
`RADIUS_HOME=.radius radius-cli wallet x402 ...` as described in
[x402-client.md](x402-client.md).

Prerequisites:
- `curl`, `jq`, `base64`, `python3`
- Foundry `cast`
- a funded Foundry keystore account imported with `cast wallet import <account> --interactive`

This flow expects a Foundry keystore account for signing. For wallet setup, follow the Radius CLI wallet convention in the **radius-dev** skill: import once with `cast wallet import <name> --interactive`, expose the account as `CAST_ACCOUNT=<name>`, derive the owner address from that account, and never pass raw private keys as CLI arguments.

The examples below use `--account "$CAST_ACCOUNT"` and may prompt for the keystore password. This is appropriate for existing local keystores, but it can hang in non-interactive agent shells.

Agent execution note: the flow below uses shell variables and `/tmp` files. Run it in one shell session, or persist and reload every variable explicitly between agent tool calls.

The flow defaults to Radius testnet. For mainnet, set `CHAIN_ID=723487`, `NETWORK=eip155:723487`, and `RPC_URL=https://rpc.radiustech.xyz`.

## 1. Configure the request

```bash
API_URL="https://your-x402-api.example.com/api/data"
CAST_ACCOUNT="radius-payer"
OWNER="$(cast wallet address --account "$CAST_ACCOUNT")"

CHAIN_ID="72344"
NETWORK="eip155:72344"
RPC_URL="https://rpc.testnet.radiustech.xyz"
SBC_TOKEN="0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb"
PERMIT2="0x000000000022D473030F116dDEE9F6B43aC78BA3"
X402_PROXY="0x402085c248EeA27D92E8b30b2C58ed07f9E20001"
```

## 2. Fetch and decode PAYMENT-REQUIRED

```bash
curl -sS -D /tmp/x402.headers -o /tmp/x402.body "$API_URL"

PAYMENT_REQUIRED="$(
  awk 'tolower($0) ~ /^payment-required:/ {sub(/\r$/,""); print substr($0, index($0,":")+2)}' /tmp/x402.headers
)"

printf '%s' "$PAYMENT_REQUIRED" | base64 -d | jq . > /tmp/x402-required.json
jq '.accepts[0]' /tmp/x402-required.json > /tmp/x402-accepted.json
```

`PAYMENT-REQUIRED` contains `accepts: [...]` because the server may advertise several payment options. The client `PAYMENT-SIGNATURE` payload sends one selected option as singular `accepted: {...}`.

## 3. Read nonces and signing values

```bash
PERMIT_NONCE="$(
  cast call "$SBC_TOKEN" "nonces(address)(uint256)" "$OWNER" --rpc-url "$RPC_URL"
)"
DEADLINE="$(($(date +%s) + 300))"
PERMIT2_NONCE="$(python3 -c 'import secrets; print(int.from_bytes(secrets.token_bytes(16), "big"))')"
AMOUNT="$(jq -r '.amount' /tmp/x402-accepted.json)"
PAY_TO="$(jq -r '.payTo' /tmp/x402-accepted.json)"
```

The EIP-2612 nonce is sequential token state from `nonces(owner)`. The Permit2 nonce is random and must not be treated as sequential.

## 4. Build EIP-712 typed data

The typed-data JSON includes `EIP712Domain` in `types` because non-viem signers such as `cast wallet sign --data` expect it.

```bash
jq -n \
  --arg chainId "$CHAIN_ID" \
  --arg token "$SBC_TOKEN" \
  --arg owner "$OWNER" \
  --arg spender "$PERMIT2" \
  --arg value "$AMOUNT" \
  --arg nonce "$PERMIT_NONCE" \
  --arg deadline "$DEADLINE" \
  '{
    types: {
      EIP712Domain: [
        {name: "name", type: "string"},
        {name: "version", type: "string"},
        {name: "chainId", type: "uint256"},
        {name: "verifyingContract", type: "address"}
      ],
      Permit: [
        {name: "owner", type: "address"},
        {name: "spender", type: "address"},
        {name: "value", type: "uint256"},
        {name: "nonce", type: "uint256"},
        {name: "deadline", type: "uint256"}
      ]
    },
    primaryType: "Permit",
    domain: {
      name: "Stable Coin",
      version: "1",
      chainId: ($chainId | tonumber),
      verifyingContract: $token
    },
    message: {
      owner: $owner,
      spender: $spender,
      value: $value,
      nonce: $nonce,
      deadline: $deadline
    }
  }' > /tmp/x402-eip2612.json

jq -n \
  --arg chainId "$CHAIN_ID" \
  --arg permit2 "$PERMIT2" \
  --arg token "$SBC_TOKEN" \
  --arg amount "$AMOUNT" \
  --arg spender "$X402_PROXY" \
  --arg nonce "$PERMIT2_NONCE" \
  --arg deadline "$DEADLINE" \
  --arg payTo "$PAY_TO" \
  '{
    types: {
      EIP712Domain: [
        {name: "name", type: "string"},
        {name: "chainId", type: "uint256"},
        {name: "verifyingContract", type: "address"}
      ],
      PermitWitnessTransferFrom: [
        {name: "permitted", type: "TokenPermissions"},
        {name: "spender", type: "address"},
        {name: "nonce", type: "uint256"},
        {name: "deadline", type: "uint256"},
        {name: "witness", type: "Witness"}
      ],
      TokenPermissions: [
        {name: "token", type: "address"},
        {name: "amount", type: "uint256"}
      ],
      Witness: [
        {name: "to", type: "address"},
        {name: "validAfter", type: "uint256"}
      ]
    },
    primaryType: "PermitWitnessTransferFrom",
    domain: {
      name: "Permit2",
      chainId: ($chainId | tonumber),
      verifyingContract: $permit2
    },
    message: {
      permitted: {token: $token, amount: $amount},
      spender: $spender,
      nonce: $nonce,
      deadline: $deadline,
      witness: {to: $payTo, validAfter: "0"}
    }
  }' > /tmp/x402-permit2.json
```

## 5. Sign with cast

```bash
EIP2612_SIGNATURE="$(
  cast wallet sign --data --from-file /tmp/x402-eip2612.json --account "$CAST_ACCOUNT"
)"

PERMIT2_SIGNATURE="$(
  cast wallet sign --data --from-file /tmp/x402-permit2.json --account "$CAST_ACCOUNT"
)"
```

## 6. Build and send PAYMENT-SIGNATURE

Hand-authored integer fields in the final payload should be decimal strings, not JSON numbers.

```bash
jq -n \
  --slurpfile accepted /tmp/x402-accepted.json \
  --arg network "$NETWORK" \
  --arg url "$API_URL" \
  --arg token "$SBC_TOKEN" \
  --arg owner "$OWNER" \
  --arg x402Proxy "$X402_PROXY" \
  --arg permit2 "$PERMIT2" \
  --arg amount "$AMOUNT" \
  --arg permit2Nonce "$PERMIT2_NONCE" \
  --arg permitNonce "$PERMIT_NONCE" \
  --arg deadline "$DEADLINE" \
  --arg permit2Signature "$PERMIT2_SIGNATURE" \
  --arg eip2612Signature "$EIP2612_SIGNATURE" \
  '{
    x402Version: 2,
    scheme: "exact",
    network: $network,
    resource: {
      url: $url,
      description: "",
      mimeType: "application/json"
    },
    accepted: $accepted[0],
    payload: {
      signature: $permit2Signature,
      permit2Authorization: {
        permitted: {token: $token, amount: $amount},
        from: $owner,
        spender: $x402Proxy,
        nonce: $permit2Nonce,
        deadline: $deadline,
        witness: {to: $accepted[0].payTo, validAfter: "0"}
      }
    },
    extensions: {
      eip2612GasSponsoring: {
        info: {
          from: $owner,
          asset: $token,
          spender: $permit2,
          amount: $amount,
          nonce: $permitNonce,
          deadline: $deadline,
          signature: $eip2612Signature,
          version: "1"
        }
      }
    }
  }' > /tmp/x402-payment-payload.json

PAYMENT_SIGNATURE="$(base64 < /tmp/x402-payment-payload.json | tr -d '\n')"

curl -sS \
  -H "PAYMENT-SIGNATURE: $PAYMENT_SIGNATURE" \
  -D /tmp/x402-paid.headers \
  "$API_URL"
```

## Debug headers

```bash
printf '%s' "$PAYMENT_REQUIRED" | base64 -d | jq .
printf '%s' "$PAYMENT_SIGNATURE" | base64 -d | jq .

PAYMENT_RESPONSE="$(
  awk 'tolower($0) ~ /^payment-response:/ {sub(/\r$/,""); print substr($0, index($0,":")+2)}' /tmp/x402-paid.headers
)"
printf '%s' "$PAYMENT_RESPONSE" | base64 -d | jq .
```

## Reference templates

The JSON templates in this directory are visual aids for agents that need to inspect the full typed-data or payment-payload shape:
- `eip2612-typed-data.template.json`
- `permit2-typed-data.template.json`
- `payment-payload.template.json`

The copy-paste CLI flow above is self-contained and does not require reading those template files from disk.
