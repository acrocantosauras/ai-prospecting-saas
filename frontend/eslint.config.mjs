import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // One-off local audit/maintenance scripts (not application code)
    "audit*.js",
    "audit*.mjs",
    "check-*.js",
    "final-audit*.js",
    "final-audit*.mjs",
    "eslint-fixes.js",
    "fix-all-errors.js",
  ]),
]);

export default eslintConfig;
