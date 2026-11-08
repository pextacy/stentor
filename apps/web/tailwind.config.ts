import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#13212E",
        slate: { paper: "#F1F4F7", rule: "#C9D2DB", mute: "#4A5A6A" },
        tape: "#F2C230",
        ok: { DEFAULT: "#1E6B45", bg: "#E3F2EA" },
        review: { DEFAULT: "#8A4B00", bg: "#FCEFD9" },
        blocked: { DEFAULT: "#A3221B", bg: "#FBE5E3" },
        fallback: { DEFAULT: "#244F94", bg: "#E4ECF8" },
      },
      fontFamily: {
        display: ["var(--font-display)", "Impact", "sans-serif"],
        sans: ["var(--font-body)", "var(--font-arabic)", "var(--font-kr)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
