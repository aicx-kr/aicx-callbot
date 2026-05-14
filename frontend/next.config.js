/** @type {import('next').NextConfig} */
const API_TARGET = process.env.BACKEND_URL || 'http://localhost:8765';

const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${API_TARGET}/api/:path*` },
      { source: '/ws/:path*', destination: `${API_TARGET}/ws/:path*` },
    ];
  },
  typedRoutes: false,
};

module.exports = nextConfig;
