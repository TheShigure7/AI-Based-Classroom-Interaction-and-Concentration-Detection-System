<template>
  <section class="page">
    <div class="page__header">
      <div>
        <h1 class="page__title">设置</h1>
        <p class="page__desc">第一版先接通视频源与基础检测参数，后续再扩展更细粒度配置。</p>
      </div>

      <button class="button button--primary" :disabled="saving" @click="handleSave">
        {{ saving ? "保存中..." : "保存设置" }}
      </button>
    </div>

    <div class="settings-grid">
      <section class="panel">
        <div class="panel__header">
          <h3>视频源设置</h3>
        </div>

        <div class="settings-form">
          <label class="field field--form">
            <span>本地摄像头</span>
            <input v-model="form.local_camera_source" />
          </label>

          <div class="field field--form">
            <span>网络视频源</span>
            <div class="inline-field">
              <input v-model="networkSourceDraft" placeholder="http://ip:8080" />
              <button
                class="button button--ghost button--compact"
                type="button"
                :disabled="addingSource || !canAddNetworkSource"
                @click="handleAddNetworkSource"
              >
                {{ addingSource ? "新增中..." : "新增" }}
              </button>
            </div>
            <div class="field-hint">新增后会立即写入后端，并同步到实时检测页的视频源列表。</div>
          </div>

          <div class="settings-history">
            <div class="settings-history__title">最近视频源</div>
            <div class="settings-history__list">
              <button
                v-for="source in form.recent_video_sources"
                :key="source.value"
                class="history-chip"
                type="button"
                @click="applyVideoSource(source.value)"
              >
                {{ source.label }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel__header">
          <h3>检测参数</h3>
        </div>

        <div class="switch-list">
          <label class="switch-row">
            <span>启用姿态分析</span>
            <input v-model="form.enable_pose_analysis" type="checkbox" />
          </label>
          <label class="switch-row">
            <span>启用睡觉检测</span>
            <input v-model="form.enable_sleeping_detection" type="checkbox" />
          </label>
          <label class="switch-row">
            <span>启用疑似交谈检测</span>
            <input v-model="form.enable_talking_detection" type="checkbox" />
          </label>
          <label class="switch-row">
            <span>保存异常截图</span>
            <input v-model="form.save_alert_snapshots" type="checkbox" />
          </label>
          <label class="switch-row">
            <span>实时提醒</span>
            <input v-model="form.enable_realtime_alerts" type="checkbox" />
          </label>
        </div>

        <label class="field field--form">
          <span>低专注阈值</span>
          <input v-model.number="form.low_attention_threshold" type="number" min="0" max="100" />
        </label>
      </section>

      <section class="panel">
        <div class="panel__header">
          <h3>提醒和总结</h3>
        </div>

        <div class="switch-list">
          <label class="switch-row">
            <span>每日总结</span>
            <input v-model="form.enable_daily_summary" type="checkbox" />
          </label>
          <label class="switch-row">
            <span>邮件总结</span>
            <input v-model="form.enable_email_summary" type="checkbox" />
          </label>
        </div>

        <label class="field field--form">
          <span>邮箱地址</span>
          <input v-model="form.email_address" placeholder="name@example.com" />
        </label>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import { getSettings, updateSettings } from "../api/realtime";

const saving = ref(false);
const addingSource = ref(false);
const networkSourceDraft = ref("");
const form = reactive({
  local_camera_source: "0",
  network_video_source: "",
  recent_video_sources: [],
  enable_pose_analysis: true,
  enable_sleeping_detection: true,
  enable_talking_detection: true,
  low_attention_threshold: 60,
  save_alert_snapshots: true,
  enable_realtime_alerts: true,
  enable_daily_summary: false,
  enable_email_summary: false,
  email_address: "",
});

const canAddNetworkSource = computed(() => Boolean(networkSourceDraft.value.trim()));

onMounted(async () => {
  const settings = await getSettings();
  Object.assign(form, settings);
  networkSourceDraft.value = settings.network_video_source ?? "";
});

async function handleSave() {
  saving.value = true;
  try {
    form.network_video_source = networkSourceDraft.value.trim();
    const settings = await updateSettings(form);
    Object.assign(form, settings);
    networkSourceDraft.value = settings.network_video_source ?? "";
  } finally {
    saving.value = false;
  }
}

async function handleAddNetworkSource() {
  const source = networkSourceDraft.value.trim();
  if (!source) {
    return;
  }

  addingSource.value = true;
  try {
    const settings = await updateSettings({
      network_video_source: source,
    });
    Object.assign(form, settings);
    networkSourceDraft.value = settings.network_video_source ?? source;
  } finally {
    addingSource.value = false;
  }
}

function applyVideoSource(value) {
  if (!value) {
    return;
  }

  if (/^\d+$/.test(value)) {
    form.local_camera_source = value;
    return;
  }

  form.network_video_source = value;
  networkSourceDraft.value = value;
}
</script>
