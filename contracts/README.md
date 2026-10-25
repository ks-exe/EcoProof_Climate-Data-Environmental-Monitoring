# Batch registry

`BatchRegistry.sol` implements the spec's owner-only, write-once registry. It also
rejects zero keys/roots, empty batches, and inverted/equal time bounds. The owner
is immutable. There is no upgrade, transfer, deletion, or overwrite function.

Use Node **22.13+** (supported even-numbered releases), Hardhat **3.20.0**, and
Solidity **0.8.20**, with the exact dependencies in `package-lock.json`.
From this directory:

```text
npm ci
npm test
npm run compile
```

In PowerShell use `npm.cmd` if execution policy prevents the `npm.ps1` shim.
Solc is installed from the locked npm package; compilation does not download a
separate compiler. Settings use the Shanghai EVM target and optimizer runs 200.
Those are compiler settings, not measured gas or performance claims.

`src/Compile.sol` imports the spec's root-level source for Solidity tests.
`npm run compile` explicitly names `BatchRegistry.sol` so Hardhat emits its
deployable artifact at `artifacts/BatchRegistry.sol/BatchRegistry.json`.
The Solidity suite exercises duplicate reverts, access control, fields/time,
empty inputs, independent keys, and 256 randomized round trips.

The Python integration suite compiles that same source and starts its own Hardhat
node on a temporary loopback port with a randomly generated local-only account.
It signs, sends, and reads actual local EVM transactions, then stops the node.
No test account is saved to `.env`, and no public RPC or wallet is used by tests.

From the repository root, deploy or resume on Ethereum Sepolia:

```text
python contracts/script/deploy
```

This wrapper uses the project's web3.py client and local `.env`, not Hardhat
wallet configuration. It requires `RPC_URL` and a funded throwaway `PRIVATE_KEY`.
The public CLI pins chain ID **11155111** and refuses other chains. The deployment
journal is `data/deployments/sepolia.json` under the configured data directory.

The October 24 run deployed the registry at
[`0xb120d4671607E7C24F6C14C4f23B589F5f4484EB`](https://sepolia.etherscan.io/address/0xb120d4671607E7C24F6C14C4f23B589F5f4484EB)
and anchored one seven-record batch on Ethereum Sepolia. See
[public receipts, anchoring commands and recovery](../docs/ANCHORING.md).
