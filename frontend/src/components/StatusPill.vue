<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral'; label: string }>(), {
  tone: 'neutral',
})
</script>

<template>
  <span class="status-pill" :class="`status-${tone}`"><i />{{ label }}</span>
</template>
