import { createRouter, createWebHistory } from "vue-router";

import AppShell from "../layout/AppShell.vue";
import AnalyticsPage from "../pages/AnalyticsPage.vue";
import RecordsPage from "../pages/RecordsPage.vue";
import RealtimePage from "../pages/RealtimePage.vue";
import SettingsPage from "../pages/SettingsPage.vue";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior() {
    return { top: 0 };
  },
  routes: [
    {
      path: "/",
      component: AppShell,
      redirect: "/realtime",
      children: [
        {
          path: "realtime",
          name: "realtime",
          component: RealtimePage,
          meta: { title: "实时检测" },
        },
        {
          path: "records",
          name: "records",
          component: RecordsPage,
          meta: { title: "检测记录" },
        },
        {
          path: "analytics",
          name: "analytics",
          component: AnalyticsPage,
          meta: { title: "分析统计" },
        },
        {
          path: "settings",
          name: "settings",
          component: SettingsPage,
          meta: { title: "设置" },
        },
      ],
    },
  ],
});

router.afterEach((to) => {
  document.title = `${to.meta?.title ?? "AI课堂互动与摸鱼检测系统"} - AI课堂互动与摸鱼检测系统`;
});

export default router;
