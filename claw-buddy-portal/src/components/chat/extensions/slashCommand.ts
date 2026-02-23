import Mention from '@tiptap/extension-mention'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import CommandTag from '../CommandTag.vue'

export const SlashCommand = Mention.extend({
  name: 'slashCommand',

  addNodeView() {
    return VueNodeViewRenderer(CommandTag)
  },
})
