import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const DIST_DIR = path.join(process.cwd(), "dist");
const MANIFEST_PATH = path.join(DIST_DIR, ".vite", "manifest.json");

const BUDGETS = {
  entry: 350 * 1024,
  initial: 500 * 1024,
  asyncDefault: 300 * 1024,
  asyncOverrides: [
    {
      name: "elk",
      pattern: /elk/i,
      limit: 450 * 1024,
    },
  ],
};

function getGzipSize(filePath) {
  try {
    const content = fs.readFileSync(filePath);
    return zlib.gzipSync(content).length;
  } catch {
    return 0;
  }
}

function collectTree(manifest, startKeys) {
  const visited = new Set();
  const queue = [...startKeys];
  while (queue.length > 0) {
    const key = queue.shift();
    if (visited.has(key)) continue;
    visited.add(key);
    const chunk = manifest[key];
    if (chunk?.imports) {
      for (const k of chunk.imports) {
        if (!visited.has(k)) queue.push(k);
      }
    }
  }
  return visited;
}

function collectAllReachable(manifest, entryKey) {
  const visited = new Set();
  const queue = [entryKey];
  while (queue.length > 0) {
    const key = queue.shift();
    if (visited.has(key)) continue;
    visited.add(key);
    const chunk = manifest[key];
    if (chunk) {
      if (chunk.imports) {
        for (const k of chunk.imports) queue.push(k);
      }
      if (chunk.dynamicImports) {
        for (const k of chunk.dynamicImports) queue.push(k);
      }
    }
  }
  return visited;
}

function getDynamicRootSyncTree(manifest, rootKey, initialTree) {
  const visited = new Set();
  const queue = [rootKey];
  while (queue.length > 0) {
    const key = queue.shift();
    if (initialTree.has(key)) continue;
    if (visited.has(key)) continue;
    visited.add(key);
    const chunk = manifest[key];
    if (chunk?.imports) {
      for (const k of chunk.imports) {
        if (!initialTree.has(k)) {
          queue.push(k);
        }
      }
    }
  }
  return visited;
}

function main() {
  console.log("Checking bundle size budgets...\n");

  if (!fs.existsSync(MANIFEST_PATH)) {
    console.error("Manifest not found at: " + MANIFEST_PATH);
    console.error("Run `npm run build` first.");
    process.exit(1);
  }

  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf-8"));

  let entryKey = null;
  let entryChunk = null;
  for (const [key, value] of Object.entries(manifest)) {
    if (value.isEntry) {
      entryKey = key;
      entryChunk = value;
      break;
    }
  }
  if (!entryChunk) {
    console.error("Could not find entry chunk in manifest.");
    process.exit(1);
  }

  const entryFilePath = path.join(DIST_DIR, entryChunk.file);
  const entryGzipSize = getGzipSize(entryFilePath);

  const initialTree = collectTree(manifest, [entryKey]);
  let totalSyncGzip = 0;
  for (const key of initialTree) {
    const chunk = manifest[key];
    if (chunk) totalSyncGzip += getGzipSize(path.join(DIST_DIR, chunk.file));
  }

  console.log("Entry chunk:       " + (entryGzipSize / 1024).toFixed(2) + " KB gzip");
  console.log("Initial sync tree: " + (totalSyncGzip / 1024).toFixed(2) + " KB gzip");

  let hasOverBudget = false;

  if (entryGzipSize > BUDGETS.entry) {
    console.error("Entry chunk exceeds " + (BUDGETS.entry / 1024).toFixed(0) + " KB budget!");
    hasOverBudget = true;
  }
  if (totalSyncGzip > BUDGETS.initial) {
    console.error("Sync tree exceeds " + (BUDGETS.initial / 1024).toFixed(0) + " KB budget!");
    hasOverBudget = true;
  }

  // 4. Collect all dynamicImports recursively
  const reachableKeys = collectAllReachable(manifest, entryKey);
  const dynamicRoots = new Set();
  for (const key of reachableKeys) {
    const chunk = manifest[key];
    if (chunk?.dynamicImports) {
      for (const dynKey of chunk.dynamicImports) {
        dynamicRoots.add(dynKey);
      }
    }
  }

  if (dynamicRoots.size > 0) {
    console.log("\nDynamic chunks (" + dynamicRoots.size + "):");
    for (const rootKey of dynamicRoots) {
      const chunk = manifest[rootKey];
      if (!chunk) continue;

      // 5. Compute its sync dependency tree
      // 6. Exclude initialTree loaded shared chunks
      const rootSyncTree = getDynamicRootSyncTree(manifest, rootKey, initialTree);

      // 7. De-duplicate files
      const files = new Set();
      for (const key of rootSyncTree) {
        const c = manifest[key];
        if (c) {
          files.add(path.join(DIST_DIR, c.file));
        }
      }

      // 8. Calculate real Gzip
      let totalGzip = 0;
      for (const filePath of files) {
        totalGzip += getGzipSize(filePath);
      }

      // 9. Apply default budget or overrides
      const override = BUDGETS.asyncOverrides.find((o) => o.pattern.test(rootKey));
      const budget = override ? override.limit : BUDGETS.asyncDefault;
      const pass = totalGzip <= budget;

      if (override) {
        if (pass) {
          console.log(`${override.name.toUpperCase()}:\n${(totalGzip / 1024).toFixed(2)} KB / ${(budget / 1024).toFixed(0)} KB\napproved override\n`);
        } else {
          console.error(`${override.name.toUpperCase()}:\n${(totalGzip / 1024).toFixed(2)} KB / ${(budget / 1024).toFixed(0)} KB\nOVER BUDGET\n`);
          hasOverBudget = true;
        }
      } else {
        const label = "default";
        console.log(`   ${rootKey} (${chunk.file}): ${(totalGzip / 1024).toFixed(2)} KB gzip  [budget: ${(budget / 1024).toFixed(0)} KB (${label})] ${pass ? "OK" : "OVER"}`);
        if (!pass) hasOverBudget = true;
      }
    }
  }

  if (hasOverBudget) {
    console.error("\nBundle budget validation FAILED.");
    process.exit(1);
  } else {
    console.log("\nBundle budget validation PASSED.");
    process.exit(0);
  }
}

main();
