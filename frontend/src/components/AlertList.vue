<template>
  <section class="panel">
    <div class="panel__header">
      <h3>行为截图列表</h3>
      <div class="alert-list__toolbar">
        <button
          v-if="canDelete && alerts.length && !selectionMode"
          class="button button--ghost button--compact"
          type="button"
          :disabled="busy"
          @click="selectionMode = true"
        >
          删除
        </button>

        <template v-if="canDelete && selectionMode">
          <span class="panel__meta">已选 {{ selectedIds.length }} 条</span>
          <button
            class="button button--ghost button--compact"
            type="button"
            :disabled="busy"
            @click="cancelSelection"
          >
            取消
          </button>
          <button
            class="button button--danger button--compact"
            type="button"
            :disabled="busy || !selectedIds.length"
            @click="submitDelete"
          >
            {{ busy ? "删除中..." : `删除选中(${selectedIds.length})` }}
          </button>
        </template>

        <span v-else class="panel__meta">最近 {{ alerts.length }} 条</span>
      </div>
    </div>

    <div v-if="alerts.length" class="alert-grid">
      <article
        v-for="alert in alerts"
        :key="alert.alert_id"
        class="alert-card"
        :class="{ 'alert-card--selecting': selectionMode, 'alert-card--selected': isSelected(alert.alert_id) }"
      >
        <label v-if="selectionMode" class="alert-card__checkbox">
          <input
            :checked="isSelected(alert.alert_id)"
            type="checkbox"
            @change="toggleSelected(alert.alert_id, $event.target.checked)"
          />
        </label>

        <img :src="alert.snapshot_url" :alt="alert.event_type" class="alert-card__image" />
        <div class="alert-card__body">
          <div class="alert-card__title">{{ eventLabel(alert.event_type) }}</div>
          <div class="alert-card__text">时间：{{ formatTime(alert.timestamp) }}</div>
          <div class="alert-card__text">学生：{{ alert.student_id }}</div>
          <div class="alert-card__text">分数：{{ alert.attention_score }}</div>
        </div>
      </article>
    </div>

    <div v-else class="empty-state">当前暂无行为截图。</div>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  alerts: {
    type: Array,
    default: () => [],
  },
  canDelete: {
    type: Boolean,
    default: false,
  },
  busy: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["delete-selected"]);

const selectionMode = ref(false);
const selectedIds = ref([]);

watch(
  () => props.alerts,
  (alerts) => {
    const availableIds = new Set(alerts.map((alert) => alert.alert_id));
    selectedIds.value = selectedIds.value.filter((id) => availableIds.has(id));
    if (!selectedIds.value.length && selectionMode.value && !alerts.length) {
      selectionMode.value = false;
    }
  },
  { deep: true }
);

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

function isSelected(alertId) {
  return selectedIds.value.includes(alertId);
}

function toggleSelected(alertId, checked) {
  if (checked) {
    if (!selectedIds.value.includes(alertId)) {
      selectedIds.value = [...selectedIds.value, alertId];
    }
    return;
  }
  selectedIds.value = selectedIds.value.filter((id) => id !== alertId);
}

function cancelSelection() {
  selectedIds.value = [];
  selectionMode.value = false;
}

function submitDelete() {
  if (!selectedIds.value.length) {
    return;
  }
  emit("delete-selected", [...selectedIds.value]);
  selectedIds.value = [];
  selectionMode.value = false;
}
</script>
