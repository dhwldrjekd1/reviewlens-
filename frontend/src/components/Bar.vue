<script setup>
import { colr } from '../lib/viz.js'
defineProps({
  name: String,
  value: Number,
  suffix: { type: String, default: '' },
  width: { type: Number, default: 88 },
})
</script>

<template>
  <div class="arow">
    <span class="nm" :style="{ width: width + 'px' }">{{ name }}</span>
    <span class="tr"><i :style="{ width: Math.max(value, 3) + '%', background: colr(value) }"></i></span>
    <span class="sc">{{ value }}{{ suffix }}</span>
  </div>
</template>
