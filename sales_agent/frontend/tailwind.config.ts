import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17211f",
        line: "#d7dfdc",
        moss: "#2f6654",
        coral: "#c8513d",
        paper: "#f7f8f5",
      },
    },
  },
  plugins: [],
};

export default config;
