<script setup lang="ts">
import AppIcon from './AppIcon.vue'

defineProps<{ icon: string; title: string; description: string }>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon"><AppIcon :name="icon" :size="26" /></div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>
