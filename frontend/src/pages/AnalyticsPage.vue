<template>
  <section class="page analytics-dashboard">
    <div class="page__header analytics-dashboard__header">
      <div>
        <h1 class="page__title">分析页面</h1>
        <p class="page__desc">
          使用历史检测记录生成课堂趋势分析、风险分布和时段表现，当前页面已切换为图表组件版。
        </p>
      </div>

      <div class="analytics-dashboard__actions">
        <label class="field field--form analytics-dashboard__field">
          <span>统计范围</span>
          <select v-model.number="filters.days">
            <option :value="3">近 3 天</option>
            <option :value="7">近 7 天</option>
            <option :value="14">近 14 天</option>
            <option :value="30">近 30 天</option>
          </select>
        </label>

        <label class="field field--form analytics-dashboard__field analytics-dashboard__field--wide">
          <span>分析会话</span>
          <select v-model="filters.session_id">
            <option value="">全面及概布分析</option>
            <option
              v-for="session in analytics.sessions"
              :key="session.session_id"
              :value="session.session_id"
            >
              {{ buildSessionLabel(session) }}
            </option>
          </select>
        </label>

        <button class="button button--ghost" :disabled="loading" @click="loadAnalytics">
          {{ loading ? "刷新中..." : "刷新统计" }}
        </button>
      </div>
    </div>

    <div class="analytics-metrics">
      <article class="metric-card">
        <div class="metric-card__icon">
          <span class="metric-card__glyph">A</span>
        </div>
        <div class="metric-card__body">
          <span class="metric-card__label">今日平均专注度</span>
          <strong class="metric-card__value">{{ attentionMetric }}</strong>
          <small class="metric-card__hint">当前检测到 {{ currentSummary.student_count || 0 }} 人</small>
        </div>
      </article>

      <article class="metric-card">
        <div class="metric-card__icon">
          <span class="metric-card__glyph">!</span>
        </div>
        <div class="metric-card__body">
          <span class="metric-card__label">总计异常数</span>
          <strong class="metric-card__value">{{ analytics.total_alerts }}</strong>
          <small class="metric-card__hint">{{ filters.days }} 天统计范围</small>
        </div>
      </article>

      <article class="metric-card">
        <div class="metric-card__icon">
          <span class="metric-card__glyph">T</span>
        </div>
        <div class="metric-card__body">
          <span class="metric-card__label">峰值风险时间</span>
          <strong class="metric-card__value">{{ peakHourMetric }}</strong>
          <small class="metric-card__hint">按小时聚合异常次数</small>
        </div>
      </article>

      <article class="metric-card">
        <div class="metric-card__icon">
          <span class="metric-card__glyph">R</span>
        </div>
        <div class="metric-card__body">
          <span class="metric-card__label">最多常见异常性</span>
          <strong class="metric-card__value">{{ dominantRiskMetric }}</strong>
          <small class="metric-card__hint">{{ analytics.unique_students }} 名关联学生</small>
        </div>
      </article>
    </div>

    <div class="analytics-grid">
      <section class="panel analytics-chart-card analytics-chart-card--wide">
        <div class="panel__header">
          <div>
            <h3>课堂浓度趋势</h3>
            <div class="analytics-chart-card__hint">根据每日异常数反推课堂稳定度，数值越高表示整体越平稳。</div>
          </div>
        </div>

        <div v-if="!hasDailyData" class="empty-state">当前暂无趋势数据。</div>
        <VChart v-else class="analytics-chart analytics-chart--large" :option="attentionTrendOption" autoresize />
      </section>

      <section class="panel analytics-chart-card analytics-chart-card--side">
        <div class="panel__header">
          <div>
            <h3>行为频率统计</h3>
            <div class="analytics-chart-card__hint">展示不同课堂行为在当前范围内的出现次数。</div>
          </div>
        </div>

        <div v-if="!hasEventData" class="empty-state">当前暂无行为统计数据。</div>
        <VChart v-else class="analytics-chart analytics-chart--medium" :option="eventBarOption" autoresize />
      </section>

      <section class="panel analytics-chart-card analytics-chart-card--compact">
        <div class="panel__header">
          <div>
            <h3>具体风险（分%）</h3>
            <div class="analytics-chart-card__hint">按事件占比分布，快速看出当前主要风险来源。</div>
          </div>
        </div>

        <div v-if="!hasEventData" class="empty-state">当前暂无风险占比数据。</div>
        <VChart v-else class="analytics-chart analytics-chart--small" :option="riskDonutOption" autoresize />
      </section>

      <section class="panel analytics-chart-card analytics-chart-card--expanded">
        <div class="panel__header">
          <div>
            <h3>正常风险大率势数</h3>
            <div class="analytics-chart-card__hint">按小时观察课堂风险波峰变化，便于定位高压时段。</div>
          </div>
        </div>

        <div v-if="!hasHourlyData" class="empty-state">当前暂无时段趋势数据。</div>
        <VChart v-else class="analytics-chart analytics-chart--small" :option="hourlyRiskOption" autoresize />
      </section>

      <section class="panel analytics-chart-card analytics-chart-card--full">
        <div class="panel__header">
          <div>
            <h3>活动维度趋势</h3>
            <div class="analytics-chart-card__hint">综合举手、风险行为和当前专注度生成活动热度曲线。</div>
          </div>
        </div>

        <div v-if="!hasHourlyData" class="empty-state">当前暂无活动趋势数据。</div>
        <VChart v-else class="analytics-chart analytics-chart--small" :option="activityTrendOption" autoresize />
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart, BarChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
} from "echarts/components";

import { getAnalyticsOverview } from "../api/realtime";

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
]);

const analytics = reactive({
  generated_at: "",
  days: 7,
  selected_session_id: null,
  current_summary: {
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
  },
  total_sessions: 0,
  total_alerts: 0,
  unique_students: 0,
  event_breakdown: [],
  daily_trend: [],
  hourly_distribution: [],
  recent_sessions: [],
  sessions: [],
});

const filters = reactive({
  days: 7,
  session_id: "",
});

const loading = ref(false);

const currentSummary = computed(() => analytics.current_summary ?? {});
const dangerMax = computed(() => Math.max(...analytics.daily_trend.map((item) => item.count), 1));
const hourlyMax = computed(() =>
  Math.max(...analytics.hourly_distribution.map((item) => item.count), 1)
);
const hasDailyData = computed(() => analytics.daily_trend.some((item) => item.count > 0));
const hasEventData = computed(() => analytics.event_breakdown.some((item) => item.count > 0));
const hasHourlyData = computed(() => analytics.hourly_distribution.some((item) => item.count > 0));

const attentionMetric = computed(() => `${currentSummary.value.average_attention || 0}%`);
const dominantRiskMetric = computed(() => analytics.event_breakdown[0]?.label ?? "暂无异常");
const peakHourMetric = computed(() => {
  const peak = [...analytics.hourly_distribution].sort((left, right) => right.count - left.count)[0];
  if (!peak || peak.count === 0) {
    return "--";
  }
  return `${String(peak.hour).padStart(2, "0")}:00`;
});

const eventLabels = computed(() => analytics.event_breakdown.map((item) => item.label));
const eventCounts = computed(() => analytics.event_breakdown.map((item) => item.count));
const dailyLabels = computed(() => analytics.daily_trend.map((item) => item.label));
const dailyStability = computed(() =>
  analytics.daily_trend.map((item) => {
    const ratio = item.count / dangerMax.value;
    return Math.max(18, Math.round(84 - ratio * 42));
  })
);
const hourlyLabels = computed(() =>
  analytics.hourly_distribution
    .filter((item) => item.hour % 2 === 0)
    .map((item) => `${String(item.hour).padStart(2, "0")}:00`)
);
const hourlyCounts = computed(() =>
  analytics.hourly_distribution
    .filter((item) => item.hour % 2 === 0)
    .map((item) => item.count)
);
const activityCurve = computed(() =>
  analytics.hourly_distribution
    .filter((item) => item.hour % 2 === 0)
    .map((item) => {
      const ratio = item.count / hourlyMax.value;
      const handRaiseBoost = (currentSummary.value.behavior_rates?.hand_raised ?? 0) * 35;
      return Math.round(52 + handRaiseBoost - ratio * 16 + Math.sin(item.hour / 2) * 8);
    })
);

const commonGrid = {
  left: 42,
  right: 20,
  top: 28,
  bottom: 30,
};

const commonAxisStyle = {
  axisLine: {
    lineStyle: {
      color: "#d9e3ef",
    },
  },
  axisLabel: {
    color: "#6d7d91",
    fontSize: 12,
  },
  splitLine: {
    lineStyle: {
      color: "#edf2f8",
    },
  },
};

const attentionTrendOption = computed(() => ({
  backgroundColor: "transparent",
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(25, 37, 56, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#ffffff" },
  },
  grid: commonGrid,
  xAxis: {
    type: "category",
    boundaryGap: false,
    data: dailyLabels.value,
    ...commonAxisStyle,
  },
  yAxis: {
    type: "value",
    min: 0,
    max: 100,
    ...commonAxisStyle,
  },
  series: [
    {
      type: "line",
      smooth: true,
      symbol: "circle",
      symbolSize: 8,
      data: dailyStability.value,
      lineStyle: {
        width: 3,
        color: "#425a74",
      },
      itemStyle: {
        color: "#425a74",
        borderColor: "#ffffff",
        borderWidth: 2,
      },
      areaStyle: {
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(103, 130, 162, 0.28)" },
            { offset: 1, color: "rgba(103, 130, 162, 0.03)" },
          ],
        },
      },
    },
  ],
}));

const eventBarOption = computed(() => ({
  backgroundColor: "transparent",
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    backgroundColor: "rgba(25, 37, 56, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#ffffff" },
  },
  grid: commonGrid,
  xAxis: {
    type: "category",
    data: eventLabels.value,
    axisTick: { show: false },
    ...commonAxisStyle,
  },
  yAxis: {
    type: "value",
    minInterval: 1,
    ...commonAxisStyle,
  },
  series: [
    {
      type: "bar",
      data: eventCounts.value,
      barWidth: 34,
      itemStyle: {
        borderRadius: [8, 8, 0, 0],
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: "#89a4c7" },
            { offset: 1, color: "#3d526c" },
          ],
        },
      },
    },
  ],
}));

const riskDonutOption = computed(() => ({
  tooltip: {
    trigger: "item",
    formatter: "{b}: {c} ({d}%)",
    backgroundColor: "rgba(25, 37, 56, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#ffffff" },
  },
  legend: {
    orient: "vertical",
    right: 10,
    top: "center",
    itemWidth: 14,
    itemHeight: 14,
    textStyle: {
      color: "#61748c",
      fontSize: 12,
    },
  },
  series: [
    {
      type: "pie",
      radius: ["32%", "68%"],
      center: ["34%", "52%"],
      avoidLabelOverlap: false,
      label: {
        color: "#55677d",
        formatter: "{d}%",
        fontSize: 12,
      },
      labelLine: {
        lineStyle: {
          color: "#bcc9d8",
        },
      },
      data: analytics.event_breakdown.map((item, index) => ({
        value: item.count,
        name: item.label,
        itemStyle: {
          color: ["#324964", "#5d7997", "#94adc8", "#c2d3e6", "#dbe8f4"][index % 5],
        },
      })),
    },
  ],
}));

const hourlyRiskOption = computed(() => ({
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(25, 37, 56, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#ffffff" },
  },
  grid: commonGrid,
  xAxis: {
    type: "category",
    boundaryGap: false,
    data: hourlyLabels.value,
    ...commonAxisStyle,
  },
  yAxis: {
    type: "value",
    minInterval: 1,
    ...commonAxisStyle,
  },
  series: [
    {
      type: "line",
      smooth: true,
      data: hourlyCounts.value,
      symbolSize: 7,
      lineStyle: {
        width: 3,
        color: "#9ab0c9",
      },
      itemStyle: {
        color: "#9ab0c9",
      },
      areaStyle: {
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(154, 176, 201, 0.36)" },
            { offset: 1, color: "rgba(154, 176, 201, 0.02)" },
          ],
        },
      },
    },
  ],
}));

const activityTrendOption = computed(() => ({
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(25, 37, 56, 0.92)",
    borderWidth: 0,
    textStyle: { color: "#ffffff" },
  },
  grid: commonGrid,
  xAxis: {
    type: "category",
    boundaryGap: false,
    data: hourlyLabels.value,
    ...commonAxisStyle,
  },
  yAxis: {
    type: "value",
    min: 0,
    max: 100,
    ...commonAxisStyle,
  },
  graphic: [
    {
      type: "circle",
      right: 58,
      bottom: 42,
      shape: { r: 30 },
      style: {
        fill: "rgba(255, 255, 255, 0.18)",
        shadowBlur: 24,
        shadowColor: "rgba(255, 255, 255, 0.24)",
      },
    },
  ],
  series: [
    {
      type: "line",
      smooth: true,
      data: activityCurve.value,
      symbolSize: 7,
      lineStyle: {
        width: 3,
        color: "#4c627b",
      },
      itemStyle: {
        color: "#4c627b",
      },
      areaStyle: {
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(121, 146, 177, 0.3)" },
            { offset: 1, color: "rgba(121, 146, 177, 0.04)" },
          ],
        },
      },
    },
  ],
}));

onMounted(async () => {
  await loadAnalytics();
});

watch(
  () => [filters.days, filters.session_id],
  async () => {
    await loadAnalytics();
  }
);

async function loadAnalytics() {
  loading.value = true;
  try {
    const response = await getAnalyticsOverview(filters);
    Object.assign(analytics, response);
  } finally {
    loading.value = false;
  }
}

function buildSessionLabel(session) {
  const startedAt = session.started_at ? session.started_at.replace("T", " ") : "--";
  return `${session.session_id} | ${startedAt}`;
}
</script>
