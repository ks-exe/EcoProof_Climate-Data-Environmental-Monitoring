import { createRequire } from "node:module";
import { defineConfig } from "hardhat/config";

const require = createRequire(import.meta.url);
// Supplied only by the Python integration-test subprocess; never read .env here.
const localTestKey = process.env.ECOPROOF_LOCAL_TEST_KEY;

export default defineConfig({
  paths: {
    sources: "./src",
    tests: { solidity: "./test" },
    cache: "./cache",
    artifacts: "./artifacts",
  },
  solidity: {
    version: "0.8.20",
    path: require.resolve("solc/soljson.js"),
    preferWasm: true,
    settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "shanghai" },
  },
  networks: {
    default: {
      type: "edr-simulated",
      chainId: 31337,
      throwOnTransactionFailures: false,
      ...(localTestKey ? { accounts: [{ privateKey: localTestKey, balance: "100000000000000000000" }] } : {}),
    },
  },
});
