<template>
  <section class="panel">
    <div class="panel__header">
      <h3>异常截图列表</h3>
      <span class="panel__meta">最近 {{ alerts.length }} 条</span>
    </div>

    <div v-if="alerts.length" class="alert-grid">
      <article v-for="alert in alerts" :key="alert.alert_id" class="alert-card">
        <img :src="alert.snapshot_url" :alt="alert.event_type" class="alert-card__image" />
        <div class="alert-card__body">
          <div class="alert-card__title">{{ eventLabel(alert.event_type) }}</div>
          <div class="alert-card__text">时间：{{ formatTime(alert.timestamp) }}</div>
          <div class="alert-card__text">学生：{{ alert.student_id }}</div>
          <div class="alert-card__text">分数：{{ alert.attention_score }}</div>
        </div>
      </article>
    </div>

    <div v-else class="empty-state">当前暂无异常截图。</div>
  </section>
</template>

<script setup>
const props = defineProps({
  alerts: {
    type: Array,
    default: () => [],
  },
});

function formatTime(timestamp) {
  return timestamp?.replace("T", " ") ?? "--";
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
  return mapping[eventType] ?? eventType;
}
</script>
