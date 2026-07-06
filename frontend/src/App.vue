<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <div class="topbar__title">AI课堂互动与摸鱼检测系统</div>
        <div class="topbar__subtitle">实时检测页 · 第一阶段联调版</div>
      </div>

      <div class="topbar__actions">
        <label class="field">
          <span>视频源</span>
          <select v-model="selectedVideoSource">
            <option
              v-for="source in settings.recent_video_sources"
              :key="source.value"
              :value="source.value"
            >
              {{ source.label }}
            </option>
            <option v-if="settings.network_video_source" :value="settings.network_video_source">
              {{ settings.network_video_source }}
            </option>
          </select>
        </label>

        <button class="button button--primary" :disabled="busy" @click="handleStart">
          开始检测
        </button>
        <button class="button button--ghost" :disabled="busy" @click="handleStop">
          停止检测
        </button>
      </div>
    </header>

    <main class="dashboard">
      <section class="hero">
        <section class="panel panel--video">
          <div class="panel__header">
            <h2>实时视频监控</h2>
            <div class="status-line">
              <span class="status-pill" :class="statusClass">{{ statusText }}</span>
              <span class="status-meta">会话：{{ sessionStatus.session_id || "--" }}</span>
              <span class="status-meta">时长：{{ formattedDuration }}</span>
            </div>
          </div>

          <div class="video-frame">
            <img
              class="video-frame__image"
              :src="videoStreamUrl"
              alt="实时检测视频流"
            />
          </div>

          <div v-if="sessionStatus.last_error" class="error-banner">
            运行错误：{{ sessionStatus.last_error }}
          </div>
        </section>

        <aside class="sidebar">
          <div class="stats-grid">
            <StatCard label="平均专注度" :value="`${classroom.summary.average_attention}%`" />
            <StatCard label="学生人数" :value="classroom.summary.student_count" />
            <StatCard label="低专注人数" :value="classroom.summary.low_attention_count" />
            <StatCard
              label="推理 FPS"
              :value="classroom.performance.inference_fps.toFixed(1)"
            />
          </div>

          <section class="panel">
            <div class="panel__header">
              <h3>行为统计</h3>
              <span class="panel__meta">当前占比</span>
            </div>

            <div class="behavior-list">
              <div
                v-for="item in behaviorItems"
                :key="item.key"
                class="behavior-list__row"
              >
                <span>{{ item.label }}</span>
                <span>{{ item.count }} 人</span>
                <span>{{ item.rate }}</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel__header">
              <h3>系统状态</h3>
            </div>

            <div class="system-info">
              <div>视频源：{{ classroom.video_source || "--" }}</div>
              <div>
                分辨率：{{ classroom.resolution.width }} x {{ classroom.resolution.height }}
              </div>
              <div>显示 FPS：{{ classroom.performance.display_fps.toFixed(1) }}</div>
              <div>状态：{{ statusText }}</div>
            </div>
          </section>
        </aside>
      </section>

      <section class="lower-grid">
        <AlertList :alerts="classroom.latest_alerts" />
        <StudentList :students="classroom.students" />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";

import AlertList from "./components/AlertList.vue";
import StatCard from "./components/StatCard.vue";
import StudentList from "./components/StudentList.vue";
import {
  createRealtimeSocket,
  getCurrentClassroom,
  getSessionStatus,
  getSettings,
  startSession,
  stopSession,
} from "./api/realtime";

const classroom = reactive({
  running: false,
  session_id: "",
  status: "idle",
  video_source: "0",
  duration_seconds: 0,
  last_error: "",
  resolution: { width: 1280, height: 720 },
  performance: { inference_fps: 0, display_fps: 0 },
  summary: {
    student_count: 0,
    average_attention: 0,
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
  },
  students: [],
  latest_alerts: [],
});

const sessionStatus = reactive({
  session_id: "",
  status: "idle",
  video_source: "0",
  started_at: null,
  stopped_at: null,
  duration_seconds: 0,
  enable_pose_analysis: true,
  save_alert_snapshots: true,
  last_error: "",
});

const settings = reactive({
  local_camera_source: "0",
  network_video_source: "",
  recent_video_sources: [{ label: "本地摄像头", value: "0" }],
});

const selectedVideoSource = ref("0");
const busy = ref(false);
let socket;

const videoStreamUrl = computed(() => `/api/v1/video/stream?ts=${Date.now()}`);

const formattedDuration = computed(() => {
  const total = sessionStatus.duration_seconds || classroom.duration_seconds || 0;
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
});

const statusText = computed(() => {
  const mapping = {
    idle: "未启动",
    running: "检测中",
    paused: "已暂停",
    stopped: "已停止",
    error: "错误",
  };
  return mapping[sessionStatus.status] ?? sessionStatus.status;
});

const statusClass = computed(() => `is-${sessionStatus.status}`);

const behaviorItems = computed(() => [
  {
    key: "hand_raised",
    label: "举手",
    count: classroom.summary.behavior_counts.hand_raised,
    rate: formatRate(classroom.summary.behavior_rates.hand_raised),
  },
  {
    key: "head_down",
    label: "低头",
    count: classroom.summary.behavior_counts.head_down,
    rate: formatRate(classroom.summary.behavior_rates.head_down),
  },
  {
    key: "phone_risk",
    label: "手机风险",
    count: classroom.summary.behavior_counts.phone_risk,
    rate: formatRate(classroom.summary.behavior_rates.phone_risk),
  },
  {
    key: "sleeping",
    label: "睡觉风险",
    count: classroom.summary.behavior_counts.sleeping,
    rate: formatRate(classroom.summary.behavior_rates.sleeping),
  },
  {
    key: "talking_risk",
    label: "疑似交谈",
    count: classroom.summary.behavior_counts.talking_risk,
    rate: formatRate(classroom.summary.behavior_rates.talking_risk),
  },
]);

onMounted(async () => {
  await bootstrap();
  connectSocket();
});

onBeforeUnmount(() => {
  socket?.close();
});

async function bootstrap() {
  const [settingsData, sessionData, classroomData] = await Promise.all([
    getSettings(),
    getSessionStatus(),
    getCurrentClassroom(),
  ]);

  Object.assign(settings, settingsData);
  Object.assign(sessionStatus, sessionData);
  Object.assign(classroom, classroomData);
  selectedVideoSource.value = sessionData.video_source || settingsData.local_camera_source || "0";
}

async function handleStart() {
  busy.value = true;
  try {
    const response = await startSession({
      video_source: selectedVideoSource.value,
      enable_pose_analysis: true,
      save_alert_snapshots: true,
    });
    Object.assign(sessionStatus, response.session);
    await refreshCurrentState();
  } finally {
    busy.value = false;
  }
}

async function handleStop() {
  busy.value = true;
  try {
    const response = await stopSession();
    Object.assign(sessionStatus, response.session);
    await refreshCurrentState();
  } finally {
    busy.value = false;
  }
}

async function refreshCurrentState() {
  const [sessionData, classroomData] = await Promise.all([
    getSessionStatus(),
    getCurrentClassroom(),
  ]);
  Object.assign(sessionStatus, sessionData);
  Object.assign(classroom, classroomData);
}

function connectSocket() {
  socket = createRealtimeSocket({
    onMessage(event) {
      classroom.performance = event.performance;
      classroom.summary = event.summary;
      classroom.latest_alerts = event.latest_alerts;
      classroom.duration_seconds = event.duration_seconds;
      classroom.status = event.status;
      sessionStatus.status = event.status;
      sessionStatus.duration_seconds = event.duration_seconds;
    },
  });
}

function formatRate(rate) {
  return `${Math.round((rate || 0) * 100)}%`;
}
</script>
