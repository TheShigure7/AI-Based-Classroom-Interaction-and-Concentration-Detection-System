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

        <button class="button button--primary" :disabled="busy" @click="handleDetectionToggle">
          {{ detectionButtonText }}
        </button>
        <button
          class="button button--ghost"
          :disabled="busy || !canTogglePlayback"
          @click="handlePlaybackToggle"
        >
          {{ playbackButtonText }}
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

          <div ref="videoFrameRef" class="video-frame" :class="{ 'is-paused': isPlaybackPaused }">
            <img
              ref="videoImageRef"
              class="video-frame__image"
              :src="displayedVideoUrl"
              alt="实时检测视频流"
            />
            <div class="video-overlay">
              <div class="video-overlay__meta">
                <span class="status-pill" :class="statusClass">{{ statusText }}</span>
                <span class="status-meta status-meta--overlay">
                  {{ sessionStatus.session_id || "--" }}
                </span>
                <span class="status-meta status-meta--overlay">{{ formattedDuration }}</span>
              </div>

              <div class="video-overlay__actions">
                <button
                  class="icon-button"
                  :class="{ 'icon-button--active': isDetectionRunning }"
                  :disabled="busy"
                  :title="detectionButtonText"
                  :aria-label="detectionButtonText"
                  @click="handleDetectionToggle"
                >
                  <svg v-if="isDetectionRunning" viewBox="0 0 24 24" aria-hidden="true">
                    <rect x="7" y="7" width="10" height="10" rx="2" />
                  </svg>
                  <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M8 6.5v11l9-5.5-9-5.5Z" />
                  </svg>
                </button>

                <button
                  class="icon-button"
                  :disabled="busy || !canTogglePlayback"
                  :title="playbackButtonText"
                  :aria-label="playbackButtonText"
                  @click="handlePlaybackToggle"
                >
                  <svg v-if="isPlaybackPaused" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M8 6.5v11l9-5.5-9-5.5Z" />
                  </svg>
                  <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                    <rect x="7" y="6.5" width="3.5" height="11" rx="1.2" />
                    <rect x="13.5" y="6.5" width="3.5" height="11" rx="1.2" />
                  </svg>
                </button>

                <button
                  class="icon-button"
                  :title="fullscreenButtonText"
                  :aria-label="fullscreenButtonText"
                  @click="toggleFullscreen"
                >
                  <svg v-if="isFullscreen" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M9 5H5v4h2V7h2V5Zm10 0h-4v2h2v2h2V5Zm-2 10v2h-2v2h4v-4h-2ZM7 15H5v4h4v-2H7v-2Z"
                    />
                  </svg>
                  <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M9 5H5v4h2V7h2V5Zm8 0h-4v2h2v2h2V5Zm0 12h-2v2h4v-4h-2v2ZM7 15H5v4h4v-2H7v-2Z"
                    />
                    <path
                      d="M10 10h4v4h-4z"
                      fill="none"
                    />
                  </svg>
                </button>
              </div>
            </div>
            <div v-if="isPlaybackPaused" class="video-frame__overlay">画面已暂停</div>
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
const isPlaybackPaused = ref(false);
const isFullscreen = ref(false);
const pausedFrameUrl = ref("");
const videoStreamNonce = ref(0);
const videoFrameRef = ref(null);
const videoImageRef = ref(null);
let socket;

const videoStreamUrl = computed(() => `/api/v1/video/stream?ts=${videoStreamNonce.value}`);
const displayedVideoUrl = computed(() =>
  isPlaybackPaused.value && pausedFrameUrl.value ? pausedFrameUrl.value : videoStreamUrl.value
);

const formattedDuration = computed(() => {
  const total = sessionStatus.duration_seconds || classroom.duration_seconds || 0;
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
});

const visualStatus = computed(() => {
  if (isPlaybackPaused.value) {
    return "paused";
  }
  return sessionStatus.status;
});

const statusText = computed(() => {
  const mapping = {
    idle: "未启动",
    running: "检测中",
    paused: "暂停中",
    stopped: "已停止",
    error: "错误",
  };
  return mapping[visualStatus.value] ?? visualStatus.value;
});

const statusClass = computed(() => `is-${visualStatus.value}`);
const isDetectionRunning = computed(() => sessionStatus.status === "running");
const detectionButtonText = computed(() =>
  isDetectionRunning.value ? "停止检测" : "开始检测"
);
const playbackButtonText = computed(() => (isPlaybackPaused.value ? "继续" : "暂停"));
const fullscreenButtonText = computed(() => (isFullscreen.value ? "退出全屏" : "全屏"));
const canTogglePlayback = computed(
  () => isDetectionRunning.value || isPlaybackPaused.value || Boolean(pausedFrameUrl.value)
);

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
  document.addEventListener("fullscreenchange", handleFullscreenChange);
});

onBeforeUnmount(() => {
  socket?.close();
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
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
    isPlaybackPaused.value = false;
    pausedFrameUrl.value = "";
    videoStreamNonce.value += 1;
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
    isPlaybackPaused.value = false;
    pausedFrameUrl.value = "";
    const response = await stopSession();
    Object.assign(sessionStatus, response.session);
    await refreshCurrentState();
  } finally {
    busy.value = false;
  }
}

async function handleDetectionToggle() {
  if (isDetectionRunning.value) {
    await handleStop();
    return;
  }
  await handleStart();
}

async function handlePlaybackToggle() {
  if (isPlaybackPaused.value) {
    isPlaybackPaused.value = false;
    pausedFrameUrl.value = "";
    videoStreamNonce.value += 1;
    await refreshCurrentState();
    return;
  }

  freezeCurrentFrame();
  isPlaybackPaused.value = true;
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
      if (isPlaybackPaused.value) {
        return;
      }
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

function freezeCurrentFrame() {
  const image = videoImageRef.value;
  if (!image || !image.naturalWidth || !image.naturalHeight) {
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context?.drawImage(image, 0, 0, canvas.width, canvas.height);
  pausedFrameUrl.value = canvas.toDataURL("image/jpeg", 0.92);
}

async function toggleFullscreen() {
  const element = videoFrameRef.value;
  if (!element) {
    return;
  }

  if (!document.fullscreenElement) {
    await element.requestFullscreen?.();
    return;
  }

  await document.exitFullscreen?.();
}

function handleFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement);
}
</script>
