#!/usr/bin/env node
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const SBC_ADDRESS = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb';

const RADIUS_DEFAULTS = {
  tokenAddress: SBC_ADDRESS,
  tokenName: 'Stable Coin',
  tokenVersion: '1',
  permit2Address: '0x000000000022D473030F116dDEE9F6B43aC78BA3',
  x402Permit2Proxy: '0x402085c248EeA27D92E8b30b2C58ed07f9E20001',
};

function usage(exitCode = 0) {
  const out = exitCode === 0 ? console.log : console.error;
  out(`Usage: node x402-pay.mjs <url> [--from <wallet-name>] [--max-amount <raw>]

Pays an x402-protected endpoint using a Radius wallet env in process.env.
Expects PRIVATE_KEY, RADIUS_CHAIN_ID, RADIUS_RPC_URL to be set
(source .radius/wallets/<name>.env first, or use --from).

Options:
  --from <name>          Auto-source ./.radius/wallets/<name>.env before running.
                         Refuses to read files with looser-than-0600 permissions.
  --max-amount <raw>     Refuse to pay if accepts[i].amount exceeds this
                         (raw 6-decimal SBC units; e.g. 10000 = 0.01 SBC).
  --help                 Show this help.

Mainnet caveat: this helper signs whatever network the wallet env says.
On mainnet (chainId 723487) payments are real money — set --max-amount.

Requires viem >= 2.0.0 in the cwd. Run "npm install viem" if missing.
`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = { url: null, from: null, maxAmount: null };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') usage(0);
    if (arg === '--from') {
      args.from = argv[++i];
      continue;
    }
    if (arg === '--max-amount') {
      args.maxAmount = argv[++i];
      continue;
    }
    if (arg.startsWith('--')) {
      console.error(`Unknown argument: ${arg}`);
      usage(1);
    }
    if (args.url) {
      console.error(`Unexpected positional argument: ${arg}`);
      usage(1);
    }
    args.url = arg;
  }
  if (!args.url) {
    console.error('Missing required <url> argument');
    usage(1);
  }
  try {
    new URL(args.url);
  } catch {
    console.error(`Invalid URL: ${args.url}`);
    process.exit(1);
  }
  if (args.maxAmount !== null && !/^[0-9]+$/.test(args.maxAmount)) {
    console.error('--max-amount must be a non-negative integer (raw 6-decimal units)');
    process.exit(1);
  }
  return args;
}

function parseEnvFile(path) {
  const env = {};
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    if (!line || line.trimStart().startsWith('#')) continue;
    const idx = line.indexOf('=');
    if (idx === -1) continue;
    env[line.slice(0, idx)] = line.slice(idx + 1);
  }
  return env;
}

function sourceWalletEnv(name) {
  if (!/^[a-zA-Z0-9._-]+$/.test(name)) {
    console.error('--from name must contain only letters, numbers, dot, underscore, or dash');
    process.exit(1);
  }
  const path = resolve(process.cwd(), '.radius', 'wallets', `${name}.env`);
  if (!existsSync(path)) {
    console.error(`Wallet env not found: ${path}`);
    console.error(`Bootstrap one with: node radius-wallet-bootstrap.mjs --name ${name} --network testnet`);
    process.exit(1);
  }
  const mode = statSync(path).mode & 0o777;
  if (mode & 0o077) {
    console.error(`Refusing to read ${path}: file mode is ${mode.toString(8)} (group/other readable).`);
    console.error(`Run: chmod 600 ${path}`);
    process.exit(1);
  }
  const env = parseEnvFile(path);
  for (const [key, value] of Object.entries(env)) {
    if (!(key in process.env)) process.env[key] = value;
  }
}

function requireEnv(keys) {
  const missing = keys.filter((k) => !process.env[k]);
  if (missing.length) {
    console.error(`Missing required env vars: ${missing.join(', ')}`);
    console.error('Source .radius/wallets/<name>.env or pass --from <name>.');
    process.exit(1);
  }
}

function randomPermit2Nonce() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return BigInt('0x' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join(''));
}

function encodeBase64Json(data) {
  return Buffer.from(JSON.stringify(data), 'utf8').toString('base64');
}

function decodeBase64Json(encoded) {
  return JSON.parse(Buffer.from(encoded, 'base64').toString('utf8'));
}

function parsePaymentRequired(response) {
  if (response.status !== 402) return null;
  const header = response.headers.get('PAYMENT-REQUIRED') ?? response.headers.get('payment-required');
  if (!header) throw new Error('402 response is missing PAYMENT-REQUIRED header');
  const body = decodeBase64Json(header);
  if (body.x402Version !== 2 || !Array.isArray(body.accepts) || !body.accepts.length) {
    throw new Error('Unexpected PAYMENT-REQUIRED format (expected x402 v2 with non-empty accepts)');
  }
  return body;
}

async function signX402Payment({ signTypedData, owner, permitNonce, resource, accepted, chainId }) {
  // Override hardcoded SBC defaults with the values the server advertised in `accepts[i]`.
  // For Radius SBC these match RADIUS_DEFAULTS exactly; for any other ERC-20 served by an
  // x402 endpoint, accepted.asset/extra carry the correct EIP-2612 domain.
  const cfg = {
    ...RADIUS_DEFAULTS,
    tokenAddress: accepted.asset ?? RADIUS_DEFAULTS.tokenAddress,
    tokenName: accepted.extra?.name ?? RADIUS_DEFAULTS.tokenName,
    tokenVersion: accepted.extra?.version ?? RADIUS_DEFAULTS.tokenVersion,
  };
  const deadline = BigInt(Math.floor(Date.now() / 1000) + 300);
  const amount = accepted.amount;

  const eip2612Signature = await signTypedData({
    domain: {
      name: cfg.tokenName,
      version: cfg.tokenVersion,
      chainId,
      verifyingContract: cfg.tokenAddress,
    },
    types: {
      Permit: [
        { name: 'owner', type: 'address' },
        { name: 'spender', type: 'address' },
        { name: 'value', type: 'uint256' },
        { name: 'nonce', type: 'uint256' },
        { name: 'deadline', type: 'uint256' },
      ],
    },
    primaryType: 'Permit',
    message: {
      owner,
      spender: cfg.permit2Address,
      value: BigInt(amount),
      nonce: permitNonce,
      deadline,
    },
  });

  const p2Nonce = randomPermit2Nonce();
  const permit2Signature = await signTypedData({
    domain: {
      name: 'Permit2',
      chainId,
      verifyingContract: cfg.permit2Address,
    },
    types: {
      PermitWitnessTransferFrom: [
        { name: 'permitted', type: 'TokenPermissions' },
        { name: 'spender', type: 'address' },
        { name: 'nonce', type: 'uint256' },
        { name: 'deadline', type: 'uint256' },
        { name: 'witness', type: 'Witness' },
      ],
      TokenPermissions: [
        { name: 'token', type: 'address' },
        { name: 'amount', type: 'uint256' },
      ],
      Witness: [
        { name: 'to', type: 'address' },
        { name: 'validAfter', type: 'uint256' },
      ],
    },
    primaryType: 'PermitWitnessTransferFrom',
    message: {
      permitted: { token: cfg.tokenAddress, amount: BigInt(amount) },
      spender: cfg.x402Permit2Proxy,
      nonce: p2Nonce,
      deadline,
      witness: { to: accepted.payTo, validAfter: 0n },
    },
  });

  const payload = {
    x402Version: 2,
    scheme: 'exact',
    network: `eip155:${chainId}`,
    resource: {
      url: resource.url,
      description: resource.description ?? '',
      mimeType: resource.mimeType ?? 'application/json',
    },
    accepted,
    payload: {
      signature: permit2Signature,
      permit2Authorization: {
        permitted: { token: cfg.tokenAddress, amount: amount.toString() },
        from: owner,
        spender: cfg.x402Permit2Proxy,
        nonce: p2Nonce.toString(),
        deadline: deadline.toString(),
        witness: { to: accepted.payTo, validAfter: '0' },
      },
    },
    extensions: {
      eip2612GasSponsoring: {
        info: {
          from: owner,
          asset: cfg.tokenAddress,
          spender: cfg.permit2Address,
          amount: amount,
          nonce: permitNonce.toString(),
          deadline: deadline.toString(),
          signature: eip2612Signature,
          version: '1',
        },
      },
    },
  };

  return encodeBase64Json(payload);
}

function viemRequire() {
  // Resolve viem from the user's cwd, not from this script's location.
  return createRequire(resolve(process.cwd(), 'package.json'));
}

async function loadFromCwd(specifier, friendlyName) {
  try {
    const req = viemRequire();
    const resolved = req.resolve(specifier);
    return await import(pathToFileURL(resolved).href);
  } catch (err) {
    if (err?.code === 'MODULE_NOT_FOUND' || err?.code === 'ERR_MODULE_NOT_FOUND') {
      console.error(`ERROR: ${friendlyName} is not installed in this directory.`);
      console.error('Run: npm install viem  (requires viem >= 2.0.0)');
      process.exit(1);
    }
    throw err;
  }
}

async function loadViem() {
  return loadFromCwd('viem', 'viem');
}

async function loadAccount() {
  return loadFromCwd('viem/accounts', 'viem/accounts');
}

function fail(code, message) {
  console.log(`status=failed`);
  console.log(`error=${code}`);
  if (message) console.log(`message=${message}`);
  process.exit(1);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.from) sourceWalletEnv(args.from);
  requireEnv(['PRIVATE_KEY', 'RADIUS_CHAIN_ID', 'RADIUS_RPC_URL']);

  const chainId = Number(process.env.RADIUS_CHAIN_ID);
  if (!Number.isInteger(chainId) || chainId <= 0) {
    fail('invalid_chain_id', `RADIUS_CHAIN_ID=${process.env.RADIUS_CHAIN_ID}`);
  }
  const rpcUrl = process.env.RADIUS_RPC_URL;
  const expectedNetwork = `eip155:${chainId}`;

  const viem = await loadViem();
  const { privateKeyToAccount } = await loadAccount();
  const { createPublicClient, http, parseAbi, defineChain } = viem;

  // Scoped to Radius networks (mainnet 723487, testnet 72344). Native-currency values are
  // RUSD on Radius and used by viem only for display; the helper signs against whatever
  // chainId the env supplies, so a non-Radius env will produce a misleading display name.
  const chain = defineChain({
    id: chainId,
    name: process.env.RADIUS_NETWORK ? `Radius ${process.env.RADIUS_NETWORK}` : `Radius (${chainId})`,
    nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
    rpcUrls: { default: { http: [rpcUrl] } },
  });

  let account;
  try {
    account = privateKeyToAccount(process.env.PRIVATE_KEY);
  } catch (err) {
    fail('invalid_private_key', err?.message ?? String(err));
  }
  const publicClient = createPublicClient({ chain, transport: http() });

  const initialRes = await fetch(args.url);
  if (initialRes.status === 200) {
    const body = await initialRes.text();
    console.log('status=free');
    console.log('http_status=200');
    console.log('');
    console.log(body);
    process.exit(0);
  }
  if (initialRes.status !== 402) {
    const body = await initialRes.text();
    console.log('status=failed');
    console.log(`http_status=${initialRes.status}`);
    console.log(`error=unexpected_status`);
    console.log('');
    console.log(body);
    process.exit(1);
  }

  let requirements;
  try {
    requirements = parsePaymentRequired(initialRes);
  } catch (err) {
    fail('invalid_payment_required', err.message);
  }

  const accepted = requirements.accepts.find((a) => a.network === expectedNetwork);
  if (!accepted) {
    const offered = requirements.accepts.map((a) => a.network).join(',');
    console.log('status=failed');
    console.log('error=network_mismatch');
    console.log(`wallet_network=${expectedNetwork}`);
    console.log(`endpoint_offers=${offered}`);
    process.exit(1);
  }

  if (args.maxAmount !== null) {
    if (BigInt(accepted.amount) > BigInt(args.maxAmount)) {
      console.log('status=failed');
      console.log('error=amount_exceeds_cap');
      console.log(`requested_amount=${accepted.amount}`);
      console.log(`max_amount=${args.maxAmount}`);
      process.exit(1);
    }
  }

  let permitNonce;
  try {
    permitNonce = await publicClient.readContract({
      address: SBC_ADDRESS,
      abi: parseAbi(['function nonces(address) view returns (uint256)']),
      functionName: 'nonces',
      args: [account.address],
    });
  } catch (err) {
    fail('rpc_nonce_read_failed', err.message);
  }

  let paymentSignature;
  try {
    paymentSignature = await signX402Payment({
      signTypedData: (params) => account.signTypedData(params),
      owner: account.address,
      permitNonce,
      resource: { url: args.url, description: `Access to ${new URL(args.url).pathname}` },
      accepted,
      chainId,
    });
  } catch (err) {
    fail('signing_failed', err.message);
  }

  const paidRes = await fetch(args.url, {
    headers: { 'PAYMENT-SIGNATURE': paymentSignature },
  });
  const respHeader = paidRes.headers.get('PAYMENT-RESPONSE') ?? paidRes.headers.get('payment-response');
  let settlement = null;
  if (respHeader) {
    try {
      settlement = decodeBase64Json(respHeader);
    } catch {
      // leave null
    }
  }
  const body = await paidRes.text();

  if (paidRes.status !== 200) {
    console.log('status=failed');
    console.log(`http_status=${paidRes.status}`);
    console.log(`error=payment_rejected`);
    if (settlement) console.log(`settlement=${JSON.stringify(settlement)}`);
    console.log('');
    console.log(body);
    process.exit(1);
  }

  console.log('status=paid');
  console.log(`http_status=${paidRes.status}`);
  console.log(`payer=${account.address}`);
  console.log(`paid_amount_raw=${accepted.amount}`);
  console.log(`paid_to=${accepted.payTo}`);
  console.log(`network=${expectedNetwork}`);
  console.log(`permit_nonce=${permitNonce.toString()}`);
  const txHash = settlement?.transaction ?? settlement?.txHash;
  if (txHash) console.log(`tx_hash=${txHash}`);
  console.log('');
  console.log(body);
}

main().catch((err) => {
  console.error('Unhandled error:', err?.stack ?? err);
  process.exit(1);
});
