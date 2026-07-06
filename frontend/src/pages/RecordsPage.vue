<template>
  <section class="page">
    <div class="page__header">
      <div>
        <h1 class="page__title">检测记录</h1>
        <p class="page__desc">第一版先展示当前运行时的异常截图记录，后续再扩展历史会话筛选。</p>
      </div>

      <button class="button button--ghost" :disabled="loading" @click="loadRecords">
        {{ loading ? "刷新中..." : "刷新记录" }}
      </button>
    </div>

    <div class="page-grid page-grid--single">
      <section class="panel records-summary">
        <div class="panel__header">
          <h3>当前记录摘要</h3>
          <span class="panel__meta">实时缓存</span>
        </div>

        <div class="records-summary__grid">
          <div class="records-summary__item">
            <span>会话状态</span>
            <strong>{{ statusLabel }}</strong>
          </div>
          <div class="records-summary__item">
            <span>记录总数</span>
            <strong>{{ alerts.length }}</strong>
          </div>
          <div class="records-summary__item">
            <span>最近学生</span>
            <strong>{{ latestStudentId }}</strong>
          </div>
          <div class="records-summary__item">
            <span>最近事件</span>
            <strong>{{ latestEventLabel }}</strong>
          </div>
        </div>
      </section>

      <AlertList :alerts="alerts" />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

import AlertList from "../components/AlertList.vue";
import { getCurrentClassroom } from "../api/realtime";

const alerts = ref([]);
const status = ref("idle");
const loading = ref(false);

const latestAlert = computed(() => alerts.value[0] ?? null);
const latestStudentId = computed(() => latestAlert.value?.student_id ?? "--");
const latestEventLabel = computed(() => eventLabel(latestAlert.value?.event_type));
const statusLabel = computed(() => {
  const mapping = {
    idle: "未启动",
    running: "检测中",
    stopped: "已停止",
    error: "错误",
  };
  return mapping[status.value] ?? status.value;
});

onMounted(async () => {
  await loadRecords();
});

async function loadRecords() {
  loading.value = true;
  try {
    const classroom = await getCurrentClassroom();
    alerts.value = classroom.latest_alerts ?? [];
    status.value = classroom.status ?? "idle";
  } finally {
    loading.value = false;
  }
}

function eventLabel(eventType) {
  const mapping = {
    hand_raised: "举手",
    head_down: "低头",
    phone_risk: "手机风险",
    sleeping: "睡觉风险",
    talking_risk: "疑似交谈",
    low_attention: "低专注",
  };
  return mapping[eventType] ?? "--";
}
</script>
