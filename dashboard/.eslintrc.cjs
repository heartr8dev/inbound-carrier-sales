// ESLint config — keeps the dashboard's TypeScript honest.
// We target the recommended rule set for React 18 + TypeScript with no
// project-aware (type-checked) rules so lint stays fast.
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  plugins: ["@typescript-eslint", "react", "react-hooks"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react/recommended",
    "plugin:react/jsx-runtime",
    "plugin:react-hooks/recommended",
  ],
  settings: { react: { version: "18" } },
  ignorePatterns: [
    "dist",
    "node_modules",
    "src/types/api.ts",
    "*.config.js",
    "*.config.cjs",
    ".eslintrc.cjs",
  ],
  rules: {
    "react/prop-types": "off",
    "@typescript-eslint/no-unused-vars": [
      "error",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
  },
};
