<template>
  <div class="tab-panel" style="display:flex; flex-direction:column; height:100%">
    <ElementsBrowser :scope="scope" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ElementsBrowser from '../ElementsBrowser.vue'

const props = defineProps({ projectId: String })
defineEmits(['dirty', 'saved'])

const scope = computed(() => `project:${props.projectId}`)
</script>
