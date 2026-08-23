/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        care: {
          50: "#f0fdfa",
          100: "#ccfbf1",
          300: "#5eead4",
          500: "#14b8a6",
          600: "#0d9488",
          700: "#0f766e",
          900: "#134e4a"
        },
        ink: "#102a43",
        mist: "#f5f8fa"
      },
      boxShadow: {
        card: "0 12px 30px -18px rgba(15, 48, 71, 0.28)",
        lift: "0 20px 45px -25px rgba(15, 48, 71, 0.36)"
      },
      borderRadius: {
        "4xl": "2rem"
      }
    }
  },
  plugins: []
};
