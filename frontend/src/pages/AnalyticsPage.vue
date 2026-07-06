<template>
  <section class="page">
    <div class="page__header">
      <div>
        <h1 class="page__title">分析统计</h1>
        <p class="page__desc">先展示当前课堂核心统计卡片，后续再接历史趋势图和聚合接口。</p>
      </div>

      <button class="button button--ghost" :disabled="loading" @click="loadAnalytics">
        {{ loading ? "刷新中..." : "刷新统计" }}
      </button>
    </div>

    <div class="page-grid">
      <StatCard label="平均专注度" :value="`${summary.average_attention}%`" />
      <StatCard label="学生人数" :value="summary.student_count" />
      <StatCard label="低专注人数" :value="summary.low_attention_count" />
      <StatCard label="睡觉风险" :value="summary.behavior_counts.sleeping" />
      <StatCard label="手机风险" :value="summary.behavior_counts.phone_risk" />
      <StatCard label="疑似交谈" :value="summary.behavior_counts.talking_risk" />
    </div>

    <section class="panel analytics-panel">
      <div class="panel__header">
        <h3>当前行为分布</h3>
      </div>

      <div class="behavior-list">
        <div v-for="item in behaviorRows" :key="item.label" class="behavior-list__row">
          <span>{{ item.label }}</span>
          <span>{{ item.count }} 人</span>
          <span>{{ item.rate }}</span>
        </div>
      </div>
    </section>

    <section class="panel analytics-panel">
      <div class="panel__header">
        <h3>课堂判断</h3>
        <span class="panel__meta">规则版本</span>
      </div>

      <div class="analytics-insights">
        <div class="analytics-insights__item">
          <span>课堂活跃度</span>
          <strong>{{ activityLevel }}</strong>
        </div>
        <div class="analytics-insights__item">
          <span>纪律风险</span>
          <strong>{{ disciplineLevel }}</strong>
        </div>
        <div class="analytics-insights__item analytics-insights__item--wide">
          <span>结论</span>
          <strong>{{ classroomConclusion }}</strong>
        </div>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import StatCard from "../components/StatCard.vue";
import { getCurrentClassroom } from "../api/realtime";

const summary = reactive({
  average_attention: 0,
  student_count: 0,
  low_attention_count: 0,
  behavior_counts: {
    hand_raised: 0,
    head_down: 0,
    phone_risk: 0,
    sleeping: 0,
    talking_risk: 0,
  },
  behavior_rates: {
    hand_raised: 0,
    head_down: 0,
    phone_risk: 0,
    sleeping: 0,
    talking_risk: 0,
  },
});
const loading = ref(false);

const behaviorRows = computed(() => [
  {
    label: "举手",
    count: summary.behavior_counts.hand_raised,
    rate: `${Math.round(summary.behavior_rates.hand_raised * 100)}%`,
  },
  {
    label: "低头",
    count: summary.behavior_counts.head_down,
    rate: `${Math.round(summary.behavior_rates.head_down * 100)}%`,
  },
  {
    label: "手机风险",
    count: summary.behavior_counts.phone_risk,
    rate: `${Math.round(summary.behavior_rates.phone_risk * 100)}%`,
  },
  {
    label: "睡觉风险",
    count: summary.behavior_counts.sleeping,
    rate: `${Math.round(summary.behavior_rates.sleeping * 100)}%`,
  },
  {
    label: "疑似交谈",
    count: summary.behavior_counts.talking_risk,
    rate: `${Math.round(summary.behavior_rates.talking_risk * 100)}%`,
  },
]);

onMounted(async () => {
  await loadAnalytics();
});

const activityLevel = computed(() => {
  const raiseRate = summary.behavior_rates.hand_raised || 0;
  if (raiseRate >= 0.25) return "高";
  if (raiseRate >= 0.1) return "中";
  return "低";
});

const disciplineLevel = computed(() => {
  const riskRate =
    (summary.behavior_rates.head_down || 0) +
    (summary.behavior_rates.phone_risk || 0) +
    (summary.behavior_rates.sleeping || 0) +
    (summary.behavior_rates.talking_risk || 0);
  if (riskRate >= 1.2) return "高";
  if (riskRate >= 0.45) return "中";
  return "低";
});

const classroomConclusion = computed(() => {
  if (disciplineLevel.value === "高") {
    return "当前课堂异常行为较多，建议优先关注低头、手机和睡觉风险。";
  }
  if (activityLevel.value === "高") {
    return "当前课堂互动表现较好，举手参与度处于较高水平。";
  }
  return "当前课堂整体平稳，可继续结合历史趋势做更准确判断。";
});

async function loadAnalytics() {
  loading.value = true;
  try {
    const classroom = await getCurrentClassroom();
    Object.assign(summary, classroom.summary);
  } finally {
    loading.value = false;
  }
}
</script>
