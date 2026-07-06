<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <div class="topbar__title">AI课堂互动与摸鱼检测系统</div>
        <div class="topbar__subtitle">课堂监测 · 记录分析 · 参数设置</div>
      </div>

      <nav class="nav-tabs" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-tabs__item"
          active-class="is-active"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </header>

    <main class="page-shell">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
const navItems = [
  { to: "/realtime", label: "实时检测" },
  { to: "/records", label: "检测记录" },
  { to: "/analytics", label: "分析统计" },
  { to: "/settings", label: "设置" },
];
</script>
