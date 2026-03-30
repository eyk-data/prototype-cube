/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./node_modules/@assistant-ui/react-ui/**/*.{js,mjs}",
  ],
  theme: {
    extend: {},
  },
  plugins: [
    require("tailwindcss-animate"),
    require("@assistant-ui/react-ui/tailwindcss"),
  ],
};
