<script setup>
import BrandMark from "./components/BrandMark.vue";
import DataUpdateControl from "./components/DataUpdateControl.vue";
import AppSettings from "./components/AppSettings.vue";
</script>

<template>
  <a class="skip-link" href="#main">跳到主要内容</a>
  <header class="app-header">
    <div class="header-inner">
      <RouterLink to="/" class="brand" aria-label="游戏资料库首页">
        <BrandMark />
        <span>游戏资料库</span>
      </RouterLink>
      <div class="header-actions"><DataUpdateControl /><AppSettings /></div>
    </div>
  </header>
  <main id="main" tabindex="-1"><RouterView /></main>
</template>
