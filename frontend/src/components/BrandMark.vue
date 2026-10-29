<script setup>
import logo from "../assets/brand-g-c.png";
</script>

<template>
  <span class="brand-g-mark" aria-hidden="true">
    <img :src="logo" alt="" width="76" height="76" draggable="false" />
  </span>
</template>

<style scoped>
.brand-g-mark {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  overflow: hidden;
  border-radius: 7px;
  vertical-align: middle;
}
.brand-g-mark img {
  position: absolute;
  display: block;
  width: 76px;
  height: 76px;
  max-width: none;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
}
</style>
