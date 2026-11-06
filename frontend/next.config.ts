import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  trailingSlash: true,
  turbopack: {
    rules: {
      // Tailwind v4 is compiled by its Turbopack loader. Without this rule the
      // `@import "tailwindcss"` is left uncompiled and no utility classes exist.
      '*.css': {
        loaders: ['@tailwindcss/turbopack'],
        as: '*.css',
      },
    },
  },
};

export default nextConfig;
