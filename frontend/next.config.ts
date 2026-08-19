import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: false, // Disable the development build indicator notion wala
};

export default nextConfig;
