import Mention from '@tiptap/extension-mention'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import CommandTag from '../CommandTag.vue'

export const SlashCommand = Mention.extend({
  name: 'slashCommand',

  addAttributes() {
    return {
      ...this.parent?.(),
      agentId: { default: null, renderHTML: () => ({}), parseHTML: () => null },
      agentLabel: { default: null, renderHTML: () => ({}), parseHTML: () => null },
    }
  },

  addNodeView() {
    return VueNodeViewRenderer(CommandTag)
  },
})
