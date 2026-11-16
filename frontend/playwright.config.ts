import { defineConfig } from "@playwright/test";
import path from "node:path";
const root = path.resolve("..");
const python = path.join(
  root,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 120000,
  expect: { timeout: 10000 },
  reporter: [["list"], ["json", { outputFile: "../var/browser-tests.json" }]],
  use: {
    baseURL: "http://127.0.0.1:8792",
    channel: process.env.PW_CHANNEL || "chrome",
    viewport: { width: 1360, height: 900 },
  },
  webServer: {
    command:
      '"' +
      python +
      '" -m uvicorn rag.main:app --host 127.0.0.1 --port 8792 --no-access-log',
    cwd: root,
    url: "http://127.0.0.1:8792/api/demo",
    reuseExistingServer: false,
    env: {
      RAG_DB: path.join(root, "var", "e2e-" + Date.now() + ".db"),
      RAG_GENERATOR: "mock",
      PYTHONUTF8: "1",
    },
  },
});
