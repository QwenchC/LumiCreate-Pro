<template>
  <div class="tn-wrap">
    <div class="eb-tree-row"
         :class="{ active: currentId === node.id }"
         :style="{ paddingLeft: (8 + depth * 12) + 'px' }"
         @click="$emit('select', node.id)"
         @dragover.prevent="onDragOver"
         @drop.prevent="onDrop">
      <span class="eb-tree-arrow"
            @click.stop="expanded = !expanded"
            :title="hasChildren ? '展开/折叠' : ''">
        {{ hasChildren ? (expanded ? '▾' : '▸') : '📁' }}
      </span>
      <span class="eb-tree-name">{{ node.name }}</span>
      <button class="tn-mini" title="重命名"
              @click.stop="$emit('rename', node)">✎</button>
      <button class="tn-mini danger" title="删除"
              @click.stop="$emit('delete', node)">✕</button>
    </div>
    <div v-if="expanded && hasChildren">
      <TreeNode v-for="child in node.children" :key="child.id"
                :node="child"
                :current-id="currentId"
                :elements-by-folder="elementsByFolder"
                :depth="depth + 1"
                @select="$emit('select', $event)"
                @rename="$emit('rename', $event)"
                @delete="$emit('delete', $event)"
                @drop-element="(eid, fid) => $emit('drop-element', eid, fid)" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  node:             { type: Object, required: true },
  currentId:        { type: Number, default: null },
  elementsByFolder: { type: Object, default: () => ({}) },
  depth:            { type: Number, default: 0 },
})
const emit = defineEmits(['select', 'rename', 'delete', 'drop-element'])

const expanded     = ref(props.depth < 1)
const hasChildren  = computed(() => !!(props.node.children || []).length)

function onDragOver(ev) { ev.dataTransfer.dropEffect = 'move' }

function onDrop(ev) {
  const eid = ev.dataTransfer?.getData('text/x-element-id')
  if (eid) {
    emit('drop-element', Number(eid), props.node.id)
  }
}
</script>

<style scoped>
.tn-wrap { user-select:none; }
.eb-tree-row {
  display:flex; align-items:center; gap:4px;
  padding:4px 8px; border-radius:4px;
  font-size:12px; cursor:pointer;
  position:relative;
}
.eb-tree-row:hover { background:var(--color-surface-2); }
.eb-tree-row.active { background:var(--color-accent-soft, rgba(80,140,220,.15)); color:var(--color-text); }
.eb-tree-arrow { width:14px; text-align:center; }
.eb-tree-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tn-mini {
  background:transparent; border:none; cursor:pointer;
  color:var(--color-text-muted); opacity:0;
  font-size:11px; padding:0 4px;
  transition:opacity .1s;
}
.eb-tree-row:hover .tn-mini { opacity:.7; }
.tn-mini:hover { opacity:1; color:var(--color-text); }
.tn-mini.danger:hover { color:var(--color-error); }
</style>
