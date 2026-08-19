<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center justify-center p-2 rounded-xl bg-teal-50 text-teal-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </span>
          <h1 class="text-2xl font-bold text-slate-900">网申助手与自动填表</h1>
        </div>
        <p class="text-slate-500 text-sm mt-1">
          对齐 NowClaw Bridge 表单映射与自动化协议，实现结构化简历一键转换为各大招聘网站标准填表 Payload。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button class="btn btn-primary text-sm shadow-sm" @click="generatePayload">
          ⚡ 生成当前平台填表 Payload
        </button>
      </div>
    </div>

    <!-- Control Panel -->
    <div class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
      <div>
        <label class="block font-bold text-slate-700 mb-1">选择目标填表简历</label>
        <select v-model="selectedResumeId" class="select w-full" @change="generatePayload">
          <option v-for="r in resumes" :key="r.id" :value="r.id">
            {{ r.name }} ({{ r.score }}分 - {{ r.targetRole }})
          </option>
        </select>
      </div>

      <div>
        <label class="block font-bold text-slate-700 mb-1">目标网申/招聘平台</label>
        <select v-model="selectedPlatform" class="select w-full" @change="generatePayload">
          <option value="nowcoder">牛客网申助手 (NowCoder Bridge)</option>
          <option value="boss">BOSS直聘 (Zhipin Form)</option>
          <option value="liepin">猎聘网 (Liepin Form)</option>
          <option value="zhilian">智联招聘 (Zhaopin Form)</option>
          <option value="custom">通用企业网申系统</option>
        </select>
      </div>

      <div class="flex items-end">
        <button class="btn btn-secondary w-full text-xs" @click="copyPayloadJson">
          📋 一键复制标准 Payload JSON
        </button>
      </div>
    </div>

    <!-- 2-Column Display -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Left: Form Field Preview Cards -->
      <div class="lg:col-span-6 space-y-4">
        <div class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm space-y-4 text-left">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 class="font-bold text-slate-900 text-sm">表单字段自动映射预览</h3>
            <span class="text-xs text-emerald-600 font-semibold">Ready to Fill</span>
          </div>

          <div v-if="loadingPayload" class="py-12 text-center text-slate-400 text-sm">正在组装表单 Payload...</div>
          <div v-else-if="!payloadResult" class="py-12 text-center text-slate-400 text-sm">
            请选择简历生成表单数据。
          </div>
          <div v-else class="space-y-3 text-xs">
            <div class="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-2">
              <span class="font-bold text-slate-800 block text-xs">【基础信息层】</span>
              <div class="grid grid-cols-2 gap-2 text-slate-600">
                <div>姓名：<span class="font-semibold text-slate-900">{{ payloadResult.form_fields?.name }}</span></div>
                <div>电话：<span class="font-semibold text-slate-900">{{ payloadResult.form_fields?.phone }}</span></div>
                <div>邮箱：<span class="font-semibold text-slate-900">{{ payloadResult.form_fields?.email }}</span></div>
                <div>学历：<span class="font-semibold text-slate-900">{{ payloadResult.form_fields?.education_level }}</span></div>
                <div>意向城市：<span class="font-semibold text-slate-900">{{ payloadResult.form_fields?.target_city }}</span></div>
                <div>期望薪资：<span class="font-semibold text-slate-900">{{ payloadResult.form_fields?.expected_salary }}</span></div>
              </div>
            </div>

            <div class="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-1.5">
              <span class="font-bold text-slate-800 block text-xs">
                【教育经历映射】({{ (payloadResult.form_fields?.educations || []).length }} 项)
              </span>
              <div v-for="(edu, eIdx) in payloadResult.form_fields?.educations" :key="eIdx" class="text-slate-600">
                • {{ edu.school }} | {{ edu.major }} | {{ edu.degree }} ({{ edu.start_date }} - {{ edu.end_date }})
              </div>
            </div>

            <div class="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-1.5">
              <span class="font-bold text-slate-800 block text-xs">
                【核心项目经历映射】({{ (payloadResult.form_fields?.project_experiences || []).length }} 项)
              </span>
              <div v-for="(proj, pIdx) in payloadResult.form_fields?.project_experiences" :key="pIdx" class="text-slate-600 border-t border-slate-200/60 pt-1.5 first:border-0 first:pt-0">
                <span class="font-bold text-slate-800">• {{ proj.project_name }} ({{ proj.role }})</span>
                <p class="text-[11px] text-slate-500 mt-0.5">{{ proj.background || proj.star_highlights }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: NowClaw Bridge / Extension Protocol JSON -->
      <div class="lg:col-span-6 space-y-4">
        <div class="bg-slate-900 text-slate-100 p-5 rounded-2xl shadow-sm space-y-3 text-left">
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span class="text-xs font-mono font-bold text-slate-300">NowClaw Bridge Contract Payload</span>
            </div>
            <button class="text-xs text-teal-400 hover:text-teal-300 font-mono" @click="copyPayloadJson">
              复制 JSON
            </button>
          </div>

          <pre class="bg-black/40 p-4 rounded-xl text-[11px] font-mono overflow-x-auto max-h-[60vh] text-emerald-400 leading-relaxed">{{ formattedJson }}</pre>

          <div class="text-xs text-slate-400 bg-white/5 p-3 rounded-xl border border-white/10">
            💡 本数据结构严格对齐 NowClaw 浏览器扩展与 Python Agent 之间的 <code class="text-teal-300">fill.state</code> Bridge 通信规范，可直接传递给 Chrome Extension / Puppeteer 执行自动化表单填充。
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { jobService, type ResumeProfile } from '@/services/jobService'

const resumes = ref<ResumeProfile[]>([])
const selectedResumeId = ref<string>('')
const selectedPlatform = ref<string>('nowcoder')
const loadingPayload = ref(false)
const payloadResult = ref<any>(null)

const formattedJson = computed(() => {
  if (!payloadResult.value) return '// 请选择简历以组装填表 Payload'
  return JSON.stringify(payloadResult.value, null, 2)
})

async function fetchResumes() {
  try {
    const res = await jobService.listResumes()
    resumes.value = res.items || []
    if (resumes.value.length) {
      selectedResumeId.value = resumes.value[0].id
      await generatePayload()
    }
  } catch (err) {
    console.error(err)
  }
}

async function generatePayload() {
  if (!selectedResumeId.value) return
  loadingPayload.value = true
  try {
    payloadResult.value = await jobService.generateAutoFillPayload({
      resume_id: selectedResumeId.value,
      platform_name: selectedPlatform.value
    })
  } catch (err) {
    console.error(err)
  } finally {
    loadingPayload.value = false
  }
}

function copyPayloadJson() {
  if (!payloadResult.value) return
  navigator.clipboard.writeText(JSON.stringify(payloadResult.value, null, 2))
  alert('已复制 NowClaw 填表 Payload JSON 到剪贴板！')
}

onMounted(() => {
  fetchResumes()
})
</script>
