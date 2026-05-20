import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        surface: {
          DEFAULT: "var(--color-surface)",
          2: "var(--color-surface-2)",
          3: "var(--color-surface-3)",
        },
        line: {
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
        },
        ink: {
          DEFAULT: "var(--color-text)",
          2: "var(--color-text-2)",
          3: "var(--color-text-3)",
        },
        accent: {
          DEFAULT: "var(--color-accent)",
          hover: "var(--color-accent-hover)",
          fg: "var(--color-accent-fg)",
          subtle: "var(--color-accent-subtle)",
        },
        ai: {
          DEFAULT: "var(--color-ai)",
          2: "var(--color-ai-2)",
          bg: "var(--color-ai-bg)",
          line: "var(--color-ai-border)",
        },
        // semantic
        ok: { DEFAULT: "#067647", bg: "#ECFDF3" },
        warn: { DEFAULT: "#B54708", bg: "#FFFAEB" },
        danger: { DEFAULT: "#B42318", bg: "#FEF3F2" },
        info: { DEFAULT: "#175CD3", bg: "#EFF8FF" },
      },
      borderRadius: {
        sm: "8px",
        md: "10px",
        lg: "14px",
        xl: "16px",
        "2xl": "20px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(20,33,61,.04), 0 4px 12px rgba(20,33,61,.06)",
        pop: "0 4px 16px rgba(20,33,61,.10), 0 2px 6px rgba(20,33,61,.06)",
        lift: "0 2px 4px rgba(20,33,61,.05), 0 8px 24px rgba(20,33,61,.10)",
        // accent-tinted emphasis glow (brand azure) for active/featured surfaces
        glow: "0 0 0 1px rgba(62,123,250,.15), 0 18px 44px -18px rgba(62,123,250,.40)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
