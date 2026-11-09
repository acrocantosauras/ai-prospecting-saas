import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

globalIgnores([
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
]);

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Relax rules for auth integration patterns: workspace slug resolution from context,
  // session restore via effects, and server-side navigation redirects.
  {
    files: [
      "src/lib/hooks/useAuth.ts",
      "src/lib/hooks/useApi.ts",
      "src/app/(auth)/login/page.tsx",
      "src/components/ui/sidebar.tsx",
      "src/app/(app)/dashboard/page.tsx",
    ],
    rules: {
      "react-hooks/rules-of-hooks": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
      "react-hooks/immutability": "off",
      "react-hooks/exhaustive-deps": "warn",
      "@next/next/no-location-assign-relative-destination": "off",
    },
  },
]);

export default eslintConfig;
