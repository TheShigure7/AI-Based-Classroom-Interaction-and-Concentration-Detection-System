<template>
  <section class="panel">
    <div class="panel__header">
      <h3>当前学生状态</h3>
      <span class="panel__meta">{{ students.length }} 人</span>
    </div>

    <div v-if="students.length" class="student-list">
      <article v-for="student in students" :key="student.student_id" class="student-list__item">
        <div>
          <div class="student-list__id">学生 {{ student.student_id }}</div>
          <div class="student-list__score">专注度 {{ student.attention_score }}</div>
        </div>
        <div class="student-tags">
          <span
            v-for="tag in buildTags(student.states)"
            :key="tag.label"
            class="student-tag"
            :class="tag.kind"
          >
            {{ tag.label }}
          </span>
        </div>
      </article>
    </div>

    <div v-else class="empty-state">当前未检测到学生。</div>
  </section>
</template>

<script setup>
defineProps({
  students: {
    type: Array,
    default: () => [],
  },
});

function buildTags(states) {
  const tags = [];
  if (states?.hand_raised) tags.push({ label: "举手", kind: "is-blue" });
  if (states?.head_down) tags.push({ label: "低头", kind: "is-yellow" });
  if (states?.phone_risk) tags.push({ label: "手机", kind: "is-red" });
  if (states?.sleeping) tags.push({ label: "睡觉", kind: "is-pink" });
  if (states?.talking_risk) tags.push({ label: "交谈", kind: "is-orange" });
  if (!tags.length) tags.push({ label: "正常", kind: "is-green" });
  return tags;
}
</script>
