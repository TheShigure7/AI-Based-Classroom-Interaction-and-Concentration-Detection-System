<template>
  <section class="page">
    <div class="page__header">
      <div>
        <h1 class="page__title">检测记录</h1>
        <p class="page__desc">当前页面已接入数据库历史记录，可按会话和异常类型筛选最近检测结果。</p>
      </div>

      <button class="button button--ghost" :disabled="loading" @click="loadRecords">
        {{ loading ? "刷新中..." : "刷新记录" }}
      </button>
    </div>

    <div class="page-grid page-grid--single">
      <section class="panel">
        <div class="panel__header">
          <h3>筛选条件</h3>
          <span class="panel__meta">历史记录查询</span>
        </div>

        <div class="records-filters">
          <label class="field field--form">
            <span>检测会话</span>
            <select v-model="filters.session_id">
              <option value="">全部会话</option>
              <option v-for="session in sessions" :key="session.session_id" :value="session.session_id">
                {{ buildSessionLabel(session) }}
              </option>
            </select>
          </label>

          <label class="field field--form">
            <span>异常类型</span>
            <select v-model="filters.event_type">
              <option value="">全部类型</option>
              <option value="hand_raised">举手</option>
              <option value="low_attention">低专注</option>
              <option value="phone_risk">手机风险</option>
              <option value="sleeping">睡觉风险</option>
              <option value="talking_risk">疑似交谈</option>
            </select>
          </label>

          <label class="field field--form">
            <span>返回条数</span>
            <select v-model.number="filters.limit">
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
          </label>
        </div>
      </section>

      <section class="panel records-summary">
        <div class="panel__header">
          <h3>记录摘要</h3>
          <span class="panel__meta">数据库结果</span>
        </div>

        <div class="records-summary__grid">
          <div class="records-summary__item">
            <span>记录总数</span>
            <strong>{{ total }}</strong>
          </div>
          <div class="records-summary__item">
            <span>当前列表</span>
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

      <AlertList
        :alerts="alerts"
        :can-delete="true"
        :busy="deleting"
        @delete-selected="handleDeleteSelected"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";

import AlertList from "../components/AlertList.vue";
import { deleteRecord, getRecords } from "../api/realtime";

const alerts = ref([]);
const total = ref(0);
const loading = ref(false);
const deleting = ref(false);
const sessions = ref([]);
const filters = reactive({
  session_id: "",
  event_type: "",
  limit: 50,
});

const latestAlert = computed(() => alerts.value[0] ?? null);
const latestStudentId = computed(() => latestAlert.value?.student_id ?? "--");
const latestEventLabel = computed(() => eventLabel(latestAlert.value?.event_type));

onMounted(async () => {
  await loadRecords();
});

watch(
  () => [filters.session_id, filters.event_type, filters.limit],
  async () => {
    await loadRecords();
  }
);

async function loadRecords() {
  loading.value = true;
  try {
    const response = await getRecords(filters);
    alerts.value = response.items ?? [];
    total.value = response.total ?? 0;
    sessions.value = response.sessions ?? [];
  } finally {
    loading.value = false;
  }
}

async function handleDeleteSelected(alertIds) {
  if (!alertIds?.length) {
    return;
  }

  const confirmed = window.confirm(`确认删除选中的 ${alertIds.length} 条记录吗？`);
  if (!confirmed) {
    return;
  }

  deleting.value = true;
  try {
    for (const alertId of alertIds) {
      await deleteRecord(alertId);
    }
    await loadRecords();
  } catch (error) {
    window.alert("删除失败，请稍后重试。");
  } finally {
    deleting.value = false;
  }
}

function buildSessionLabel(session) {
  const startedAt = session.started_at ? session.started_at.replace("T", " ") : "--";
  return `${session.session_id} | ${startedAt}`;
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
