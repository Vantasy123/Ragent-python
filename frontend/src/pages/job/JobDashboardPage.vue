<template>
  <div class="space-y-6">
    <!-- Top Header -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center justify-center p-2 rounded-xl bg-blue-50 text-blue-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </span>
          <h1 class="text-2xl font-bold text-slate-900">求职数据分析大盘</h1>
        </div>
        <p class="text-slate-500 text-sm mt-1">
          全周期求职投递转化漏斗、面试推进率、Offer 转化率与 AI 策略建议。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button class="btn btn-primary text-sm" @click="fetchStats">
          刷新统计数据
        </button>
      </div>
    </div>

    <!-- 4 Key Metric Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm text-left">
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">投递总岗位数</span>
        <div class="text-3xl font-black text-slate-900 mt-2">{{ stats?.total_applications || 0 }}</div>
        <div class="text-xs text-slate-500 mt-1">其中已网申 {{ stats?.applied_count || 0 }} 家企业</div>
      </div>

      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm text-left">
        <span class="text-xs font-bold text-indigo-400 uppercase tracking-wider">面试转化率</span>
        <div class="text-3xl font-black text-indigo-600 mt-2">{{ stats?.interview_rate || 0 }}%</div>
        <div class="text-xs text-slate-500 mt-1">进入面试 {{ stats?.interview_count || 0 }} 次</div>
      </div>

      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm text-left">
        <span class="text-xs font-bold text-emerald-400 uppercase tracking-wider">Offer 斩获数</span>
        <div class="text-3xl font-black text-emerald-600 mt-2">{{ stats?.offer_count || 0 }}</div>
        <div class="text-xs text-slate-500 mt-1">Offer 达成率 {{ stats?.offer_rate || 0 }}%</div>
      </div>

      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm text-left">
        <span class="text-xs font-bold text-purple-400 uppercase tracking-wider">AI 求职助理状态</span>
        <div class="text-lg font-bold text-purple-600 mt-2">Active & Ready</div>
        <div class="text-xs text-slate-500 mt-1">NowClaw 引擎驱动中</div>
      </div>
    </div>

    <!-- Funnel and Distribution -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Funnel Chart Card -->
      <div class="lg:col-span-7 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-4 text-left">
        <h3 class="font-bold text-slate-900 text-base border-b border-slate-100 pb-3">求职投递转化漏斗</h3>

        <div class="space-y-4 pt-2">
          <div v-for="item in (stats?.funnel || [])" :key="item.key" class="space-y-1">
            <div class="flex items-center justify-between text-xs">
              <span class="font-semibold text-slate-700">{{ item.stage }}</span>
              <span class="font-bold text-slate-900">{{ item.count }} 个</span>
            </div>
            <div class="w-full h-3 bg-slate-100 rounded-full overflow-hidden">
              <div
                class="h-full bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-500"
                :style="{ width: `${Math.max(8, Math.min(100, (item.count / Math.max(1, stats?.total_applications || 1)) * 100))}%` }"
              ></div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI Strategy Tips Card -->
      <div class="lg:col-span-5 bg-gradient-to-br from-slate-900 to-indigo-950 text-white p-6 rounded-2xl shadow-sm space-y-4 text-left">
        <h3 class="font-bold text-indigo-200 text-base border-b border-white/10 pb-3">💡 AI 求职策略周报</h3>

        <div class="space-y-3 text-xs text-slate-300 leading-relaxed">
          <p>
            • <strong class="text-white">高回复率建议：</strong>针对字节、阿里等大厂 JD，建议先在【岗位匹配】中运行 AI 深度诊断，使用自动生成的高情商 HR 破冰语。
          </p>
          <p>
            • <strong class="text-white">面试通关技巧：</strong>面试前前往【AI 模拟面试厅】针对目标职位进行 3 轮专项出题对练，重点突破高并发与系统设计。
          </p>
          <p>
            • <strong class="text-white">网申批量提效：</strong>通过【网申助手】将结构化简历导出为标准 NowClaw Bridge 格式，提升网申填表效率 80% 以上。
          </p>
        </div>

        <div class="pt-3 border-t border-white/10 flex justify-between items-center">
          <span class="text-xs text-indigo-300">Ragent 求职助手</span>
          <router-link to="/chat" class="btn btn-primary text-xs !bg-blue-600 hover:!bg-blue-700">
            进入智能求职对话 ➔
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { jobService } from '@/services/jobService'

const stats = ref<any>(null)

async function fetchStats() {
  try {
    stats.value = await jobService.getDashboardStats()
  } catch (err) {
    console.error(err)
  }
}

onMounted(() => {
  fetchStats()
})
</script>
