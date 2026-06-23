/**
 * verify-production.mjs
 *
 * Post-build verification script to ensure mock data, MSW setup,
 * and dev-only reset endpoints do NOT leak into the production bundle.
 *
 * Usage: node scripts/verify-production.mjs
 */

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, extname } from "node:path";

const DIST_DIR = join(process.cwd(), "dist");

const FORBIDDEN_PATTERNS = [
  { pattern: "setupWorker", description: "MSW browser worker setup" },
  { pattern: "__mock__/reset", description: "Mock database reset endpoint" },
  { pattern: "verify-e2e-user", description: "E2E verification helper" },
  { pattern: "reset-e2e-user", description: "E2E reset helper" },
];

// Only scan .js and .css assets
const SCAN_EXTENSIONS = new Set([".js", ".css", ".mjs"]);

function collectFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(fullPath));
    } else if (SCAN_EXTENSIONS.has(extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

function main() {
  console.log("🔍 Scanning production build for forbidden patterns...\n");

  let hasErrors = false;

  try {
    statSync(DIST_DIR);
  } catch {
    console.error("❌ dist/ directory not found. Run `npm run build` first.");
    process.exit(1);
  }

  // Verify mockServiceWorker.js does not exist in dist/
  const mswWorkerPath = join(DIST_DIR, "mockServiceWorker.js");
  if (existsSync(mswWorkerPath)) {
    console.error("❌ FOUND mockServiceWorker.js in dist/ directory. This is not allowed in production!\n");
    hasErrors = true;
  }

  const files = collectFiles(DIST_DIR);

  if (files.length === 0) {
    console.error("❌ No .js/.css files found in dist/. Build may have failed.");
    process.exit(1);
  }

  console.log(`  Scanning ${files.length} files in dist/\n`);

  for (const filePath of files) {
    const content = readFileSync(filePath, "utf-8");
    const relativePath = filePath.replace(process.cwd() + "\\", "").replace(process.cwd() + "/", "");

    for (const { pattern, description } of FORBIDDEN_PATTERNS) {
      if (content.includes(pattern)) {
        console.error(`  ❌ FOUND "${pattern}" in ${relativePath}`);
        console.error(`     → ${description} should not be in production bundle\n`);
        hasErrors = true;
      }
    }
  }

  // Check bundle size (warn if over 3MB uncompressed)
  const jsFiles = files.filter((f) => f.endsWith(".js") || f.endsWith(".mjs"));
  let totalJsSize = 0;
  for (const f of jsFiles) {
    totalJsSize += statSync(f).size;
  }
  const totalJsSizeKB = (totalJsSize / 1024).toFixed(1);
  const totalJsSizeMB = (totalJsSize / 1024 / 1024).toFixed(2);

  console.log(`  📦 Total JS bundle size: ${totalJsSizeKB} KB (${totalJsSizeMB} MB)`);

  if (totalJsSize > 3 * 1024 * 1024) {
    console.warn(`  ⚠️  WARNING: Total JS exceeds 3 MB. Consider code splitting.\n`);
  }

  if (hasErrors) {
    console.error("\n❌ Production verification FAILED. Mock code detected in bundle.");
    process.exit(1);
  } else {
    console.log("\n✅ Production verification PASSED. No mock code in bundle.");
    process.exit(0);
  }
}

main();
