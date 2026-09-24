/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        stevens: {
          red: "#A32537",
          reddark: "#7E1C2B",
          blue: "#00427F",
          bluedark: "#002F5B",
          medblue: "#4895CF",
          gray: "#7F7F7F",
          darkgray: "#363D45",
          lightgray: "#E3E5E6",
          lightblue: "#E7F2FB",
          gold: "#EBC73A",
          orange: "#E6832E",
          ink: "#363D45",
        },
      },
      fontFamily: {
        sans: ["Arial", "Helvetica", "system-ui", "sans-serif"],
      },
      boxShadow: {
        studio: "0 24px 60px rgba(0,66,127,0.16)",
        card: "0 10px 30px rgba(0,66,127,0.10)",
        glow: "0 0 0 1px rgba(163,37,55,0.15), 0 18px 40px rgba(163,37,55,0.18)",
      },
      borderRadius: {
        xl2: "1rem",
      },
      backgroundImage: {
        "stevens-hero":
          "radial-gradient(1200px 400px at 15% -10%, rgba(72,149,207,0.18), transparent 60%), radial-gradient(900px 500px at 110% 10%, rgba(163,37,55,0.12), transparent 55%)",
      },
      keyframes: {
        "pop-in": {
          "0%": { transform: "scale(0.9)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
      animation: {
        "pop-in": "pop-in 0.35s ease-out",
      },
    },
  },
  plugins: [],
};
