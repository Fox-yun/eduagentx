import { rmSync, existsSync } from "node:fs";
import { join } from "node:path";

const DIST_DIR = join(process.cwd(), "dist");
const MSW_SW_PATH = join(DIST_DIR, "mockServiceWorker.js");

function main() {
  console.log("🧹 Running post-build cleanups...");
  if (existsSync(MSW_SW_PATH)) {
    try {
      rmSync(MSW_SW_PATH, { force: true });
      console.log("   ✅ Removed mockServiceWorker.js from production dist/");
    } catch (err) {
      console.error("   ❌ Failed to remove mockServiceWorker.js:", err.message);
      process.exit(1);
    }
  } else {
    console.log("   ℹ️ mockServiceWorker.js not found in dist/, skipping deletion.");
  }
}

main();
