/** @type {import('next').NextConfig} */
const nextConfig = {
  // Requerido para la imagen Docker con output mínimo (Dockerfile.frontend)
  output: "standalone",

  // Proxy inverso hacia el backend FastAPI desde el servidor Next.js
  // (evita exponer el API directamente al browser en prod)
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://api:8000"}/:path*`,
      },
    ];
  },

  // Imágenes externas permitidas (ajustar según necesidad)
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
};

export default nextConfig;
