<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <div class="topbar__title">AI课堂互动与摸鱼检测系统</div>
        <div class="topbar__subtitle">课堂监测 · 记录分析 · 参数设置</div>
      </div>

      <div class="topbar__actions">
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

        <button
          class="topbar__close"
          type="button"
          title="退出程序"
          aria-label="退出程序"
          :disabled="exiting"
          @click="handleExitApplication"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M7.05 7.05a1 1 0 0 1 1.414 0L12 10.586l3.536-3.536a1 1 0 1 1 1.414 1.414L13.414 12l3.536 3.536a1 1 0 0 1-1.414 1.414L12 13.414 8.464 16.95a1 1 0 0 1-1.414-1.414L10.586 12 7.05 8.464a1 1 0 0 1 0-1.414Z"
            />
          </svg>
        </button>
      </div>
    </header>

    <main class="page-shell">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { ref } from "vue";

import { exitApplication } from "../api/realtime";

const navItems = [
  { to: "/realtime", label: "实时检测" },
  { to: "/records", label: "检测记录" },
  { to: "/analytics", label: "分析统计" },
  { to: "/settings", label: "设置" },
];

const exiting = ref(false);

async function handleExitApplication() {
  const confirmed = window.confirm("确认退出课堂检测程序吗？");
  if (!confirmed) {
    return;
  }

  exiting.value = true;
  try {
    await exitApplication();
  } catch (error) {
    window.alert("退出失败，请尝试使用关闭课堂检测脚本。");
    exiting.value = false;
    return;
  }

  setTimeout(() => {
    window.location.replace("about:blank");
  }, 500);
}
</script>
