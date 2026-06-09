<script setup>
import { computed } from 'vue'
import { Smile, Meh, Frown } from 'lucide-vue-next'
const props = defineProps({ score: { type: Number, default: 80 }, size: { type: Number, default: 17 } })
const icon = computed(() => (props.score >= 80 ? Smile : props.score >= 60 ? Meh : Frown))
const color = computed(() => (props.score >= 80 ? '#1fbf8f' : props.score >= 60 ? '#f5a623' : '#ef5878'))
</script>

<template>
  <component :is="icon" :size="size" :color="color" />
</template>
