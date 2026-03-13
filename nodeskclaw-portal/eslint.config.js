import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import parserVue from 'vue-eslint-parser'

export default [
  {
    ignores: ['dist/', 'node_modules/', '*.d.ts'],
  },
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ['**/*.ts', '**/*.tsx', '**/*.vue'],
  })),
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parser: parserVue,
      parserOptions: {
        parser: tseslint.parser,
        sourceType: 'module',
      },
    },
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'warn',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/html-indent': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/attribute-hyphenation': 'off',
      'vue/v-on-event-hyphenation': 'off',
      'vue/require-default-prop': 'off',
    },
  },
]
