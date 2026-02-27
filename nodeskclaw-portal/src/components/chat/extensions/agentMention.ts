import Mention from '@tiptap/extension-mention'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import MentionTag from '../MentionTag.vue'

export const AgentMention = Mention.extend({
  name: 'agentMention',

  addAttributes() {
    return {
      ...this.parent?.(),
      status: { default: null, renderHTML: () => ({}), parseHTML: () => null },
      slug: { default: null, renderHTML: () => ({}), parseHTML: () => null },
    }
  },

  addNodeView() {
    return VueNodeViewRenderer(MentionTag)
  },
})
