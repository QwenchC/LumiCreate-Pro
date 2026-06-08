<template>
  <MusicGenerator scope="project" :project-id="projectId" />
</template>

<script setup>
import MusicGenerator from '../MusicGenerator.vue'

defineProps({ projectId: String })
</script>
