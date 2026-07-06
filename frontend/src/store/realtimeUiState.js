import { ref } from "vue";

export const selectedVideoSource = ref("0");
export const isPlaybackPaused = ref(false);
export const pausedFrameUrl = ref("");
export const videoStreamNonce = ref(0);

export function resumeRealtimePlayback() {
  isPlaybackPaused.value = false;
  pausedFrameUrl.value = "";
  videoStreamNonce.value += 1;
}
