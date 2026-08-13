import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  // Output minimal untuk Docker production image (lihat frontend/Dockerfile stage "runner")
  output: "standalone",
};

export default nextConfig;
