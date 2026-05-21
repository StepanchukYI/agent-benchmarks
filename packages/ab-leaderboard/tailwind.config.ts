import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Tailwind tokens for ab-leaderboard.
 *
 * Every custom color uses the `<alpha-value>` placeholder so opacity modifiers
 * (`bg-pass/[0.12]`, `text-accent/50`) work against CSS-variable-backed HSL
 * channels. HSL channels themselves live in `src/styles/globals.css`.
 */
const hsl = (cssVar: string): string => `hsl(var(--${cssVar}) / <alpha-value>)`;

const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: hsl("border"),
        "border-soft": hsl("border-soft"),
        input: hsl("input"),
        ring: hsl("ring"),
        background: hsl("background"),
        "background-2": hsl("background-2"),
        foreground: hsl("foreground"),
        "foreground-2": hsl("foreground-2"),
        muted: {
          DEFAULT: hsl("muted"),
          foreground: hsl("muted-foreground"),
        },
        panel: {
          DEFAULT: hsl("panel"),
          2: hsl("panel-2"),
          3: hsl("panel-3"),
        },
        primary: {
          DEFAULT: hsl("primary"),
          foreground: hsl("primary-foreground"),
        },
        accent: {
          DEFAULT: hsl("accent"),
          foreground: hsl("accent-foreground"),
        },
        secondary: {
          DEFAULT: hsl("secondary"),
          foreground: hsl("secondary-foreground"),
        },
        destructive: {
          DEFAULT: hsl("destructive"),
          foreground: hsl("destructive-foreground"),
        },
        popover: {
          DEFAULT: hsl("popover"),
          foreground: hsl("popover-foreground"),
        },
        card: {
          DEFAULT: hsl("card"),
          foreground: hsl("card-foreground"),
        },
        pass: hsl("pass"),
        fail: hsl("fail"),
        warn: hsl("warn"),
        info: hsl("info"),
        idle: hsl("idle"),
        vendor: {
          anthropic: hsl("vendor-anthropic"),
          openai: hsl("vendor-openai"),
          google: hsl("vendor-google"),
          zhipu: hsl("vendor-zhipu"),
          minimax: hsl("vendor-minimax"),
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        pop: "0 0 0 1px hsl(var(--border)), 0 18px 40px -8px rgba(0,0,0,.35)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.6" },
          "70%": { transform: "scale(2.4)", opacity: "0" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 1.6s cubic-bezier(0,0,0.2,1) infinite",
      },
    },
  },
  plugins: [animate],
};

export default config;
