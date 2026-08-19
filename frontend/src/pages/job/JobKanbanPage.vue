<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center justify-center p-2 rounded-xl bg-amber-50 text-amber-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
            </svg>
          </span>
          <h1 class="text-2xl font-bold text-slate-900">求职投递看板</h1>
        </div>
        <p class="text-slate-500 text-sm mt-1">
          全流程求职追踪看板，支持阶段拖拽流转、面试日程复盘记录与 Offer 薪酬包对比。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <router-link to="/admin/job-matching" class="btn btn-secondary text-sm">
          去岗位库挑选 +
        </router-link>
        <button class="btn btn-primary text-sm" @click="fetchApplications">
          刷新看板
        </button>
      </div>
    </div>

    <!-- Quick Stats Bar -->
    <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
        <span class="text-xs font-semibold text-slate-400">总投递/跟进</span>
        <div class="text-2xl font-black text-slate-900 mt-1">{{ applications.length }}</div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
        <span class="text-xs font-semibold text-slate-400">已网申投递</span>
        <div class="text-2xl font-black text-blue-600 mt-1">{{ countByStage('applied') }}</div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
        <span class="text-xs font-semibold text-slate-400">笔试/初筛中</span>
        <div class="text-2xl font-black text-indigo-600 mt-1">{{ countByStage('screening') + countByStage('assessment') }}</div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
        <span class="text-xs font-semibold text-slate-400">面试进行中</span>
        <div class="text-2xl font-black text-purple-600 mt-1">{{ countByStage('interview_1') + countByStage('interview_2') + countByStage('hr_interview') }}</div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
        <span class="text-xs font-semibold text-slate-400">斩获 Offer</span>
        <div class="text-2xl font-black text-emerald-600 mt-1">{{ countByStage('offer') }}</div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
        <span class="text-xs font-semibold text-slate-400">已归档/淘汰</span>
        <div class="text-2xl font-black text-slate-400 mt-1">{{ countByStage('rejected') + countByStage('withdrawn') }}</div>
      </div>
    </div>

    <!-- Kanban Columns Grid -->
    <div class="flex gap-4 overflow-x-auto pb-6 pt-2 items-start min-h-[600px]">
      <div
        v-for="col in columns"
        :key="col.stage"
        class="w-72 shrink-0 bg-slate-100/80 rounded-2xl border border-slate-200 p-3 flex flex-col max-h-[75vh]"
      >
        <!-- Column Header -->
        <div class="flex items-center justify-between px-2 py-1.5 mb-2">
          <div class="flex items-center gap-2">
            <span :class="['w-2.5 h-2.5 rounded-full', col.badgeClass]"></span>
            <span class="text-xs font-bold text-slate-800">{{ col.title }}</span>
          </div>
          <span class="px-2 py-0.5 text-xs font-bold bg-white text-slate-600 rounded-full shadow-2xs">
            {{ getCardsByStage(col.stage).length }}
          </span>
        </div>

        <!-- Cards Container -->
        <div class="space-y-3 overflow-y-auto pr-1 flex-1 min-h-[120px]">
          <div
            v-if="!getCardsByStage(col.stage).length"
            class="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-300 rounded-xl"
          >
            暂无卡片
          </div>

          <div
            v-for="app in getCardsByStage(col.stage)"
            :key="app.id"
            class="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs hover:shadow-sm hover:border-slate-300 transition-all space-y-2.5 text-left"
          >
            <div class="flex items-start justify-between gap-2">
              <div>
                <h4 class="font-bold text-slate-900 text-sm leading-snug">{{ app.jobTitle }}</h4>
                <div class="text-xs font-semibold text-purple-700 mt-0.5">{{ app.company }}</div>
              </div>
              <span class="text-xs font-bold text-rose-600 whitespace-nowrap">
                {{ app.salaryMin }}-{{ app.salaryMax }}K
              </span>
            </div>

            <div class="text-[11px] text-slate-500 flex flex-wrap items-center gap-2">
              <span>📍 {{ app.city }}</span>
              <span>•</span>
              <span>渠道: {{ app.applyChannel }}</span>
            </div>

            <div v-if="app.notes" class="text-xs bg-slate-50 p-2 rounded-lg text-slate-600 border border-slate-100">
              {{ app.notes }}
            </div>

            <div v-if="app.interviewRecords?.length" class="text-[11px] bg-purple-50 p-2 rounded-lg text-purple-900 border border-purple-100">
              <span class="font-bold">最新面试：</span>
              {{ app.interviewRecords[app.interviewRecords.length - 1].round_title }}
              ({{ app.interviewRecords[app.interviewRecords.length - 1].interview_time }})
            </div>

            <div v-if="app.stage === 'offer' && app.offerDetails" class="text-[11px] bg-emerald-50 p-2 rounded-lg text-emerald-900 border border-emerald-100">
              <span class="font-bold">🎉 Offer 薪资：</span>{{ app.offerDetails.salary || '已发 Offer' }}
            </div>

            <!-- Card Actions -->
            <div class="pt-2 border-t border-slate-100 flex items-center justify-between gap-1 text-xs">
              <select
                :value="app.stage"
                class="select !py-0.5 !px-1 text-[11px] h-7 border-slate-200 text-slate-700 font-medium"
                @change="handleStageChange(app.id, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="c in columns" :key="c.stage" :value="c.stage">{{ c.title }}</option>
              </select>

              <div class="flex items-center gap-1">
                <button class="p-1 text-slate-400 hover:text-purple-600" title="添加面试日程" @click="openInterviewModal(app)">
                  📅
                </button>
                <button class="p-1 text-slate-400 hover:text-emerald-600" title="记录 Offer" @click="openOfferModal(app)">
                  💰
                </button>
                <button class="p-1 text-slate-400 hover:text-rose-600" title="删除" @click="handleDelete(app.id)">
                  ✕
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Interview Schedule Modal -->
    <div v-if="showInterviewModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        <div class="p-5 border-b border-slate-100 flex items-center justify-between">
          <h3 class="text-base font-bold text-slate-900">📅 添加面试日程与复盘记录</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="showInterviewModal = false">✕</button>
        </div>

        <div class="p-6 space-y-3 text-xs">
          <div>
            <label class="block font-bold text-slate-700 mb-1">面试轮次</label>
            <input v-model="formInterviewRound" type="text" class="input w-full" placeholder="例如：技术一面 / 总监面 / HR面" />
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">面试时间</label>
            <input v-model="formInterviewTime" type="text" class="input w-full" placeholder="例如：2026-08-25 15:00" />
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">面试官/岗位信息</label>
            <input v-model="formInterviewer" type="text" class="input w-full" placeholder="例如：后端技术专家" />
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">面试高频提问与复盘笔记</label>
            <textarea v-model="formInterviewFeedback" rows="4" class="textarea w-full" placeholder="记录被问到的八股、项目难点与自我表现复盘..."></textarea>
          </div>
        </div>

        <div class="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
          <button class="btn btn-secondary text-xs" @click="showInterviewModal = false">取消</button>
          <button class="btn btn-primary text-xs" @click="saveInterviewRecord">保存记录</button>
        </div>
      </div>
    </div>

    <!-- Offer Modal -->
    <div v-if="showOfferModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        <div class="p-5 border-b border-slate-100 flex items-center justify-between">
          <h3 class="text-base font-bold text-slate-900">🎉 记录录用 Offer 详情</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="showOfferModal = false">✕</button>
        </div>

        <div class="p-6 space-y-3 text-xs">
          <div>
            <label class="block font-bold text-slate-700 mb-1">薪酬待遇 (Total Package)</label>
            <input v-model="formOfferSalary" type="text" class="input w-full" placeholder="例如：30k * 16薪 + 股票期权" />
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">福利与补贴</label>
            <input v-model="formOfferBenefits" type="text" class="input w-full" placeholder="例如：房补 1500/月、免费三餐、全额六险一金" />
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">最晚确认截止日期 (Deadline)</label>
            <input v-model="formOfferDeadline" type="text" class="input w-full" placeholder="例如：2026-09-01" />
          </div>
        </div>

        <div class="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
          <button class="btn btn-secondary text-xs" @click="showOfferModal = false">取消</button>
          <button class="btn btn-primary text-xs" @click="saveOfferRecord">保存 Offer</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { jobService, type JobApplicationItem } from '@/services/jobService'

const applications = ref<JobApplicationItem[]>([])
const activeApp = ref<JobApplicationItem | null>(null)

const showInterviewModal = ref(false)
const formInterviewRound = ref('技术一面')
const formInterviewTime = ref('2026-08-25 14:00')
const formInterviewer = ref('资深技术专家')
const formInterviewFeedback = ref('')

const showOfferModal = ref(false)
const formOfferSalary = ref('28k * 15薪')
const formOfferBenefits = ref('房补 + 六险一金 + 免费三餐')
const formOfferDeadline = ref('2026-09-05')

const columns = [
  { stage: 'wishlist', title: '心仪意向', badgeClass: 'bg-slate-400' },
  { stage: 'applied', title: '已网申/投递', badgeClass: 'bg-blue-500' },
  { stage: 'screening', title: '简历初筛', badgeClass: 'bg-cyan-500' },
  { stage: 'assessment', title: '笔试测评', badgeClass: 'bg-indigo-500' },
  { stage: 'interview_1', title: '技术一面', badgeClass: 'bg-purple-500' },
  { stage: 'interview_2', title: '技术二面/总监面', badgeClass: 'bg-pink-500' },
  { stage: 'hr_interview', title: 'HR 终面', badgeClass: 'bg-amber-500' },
  { stage: 'offer', title: '斩获 Offer', badgeClass: 'bg-emerald-500' },
  { stage: 'rejected', title: '未通过/淘汰', badgeClass: 'bg-rose-400' },
]

async function fetchApplications() {
  try {
    const res = await jobService.listApplications()
    applications.value = res.items || []
  } catch (err) {
    console.error(err)
  }
}

function getCardsByStage(stage: string) {
  return applications.value.filter(a => a.stage === stage)
}

function countByStage(stage: string) {
  return applications.value.filter(a => a.stage === stage).length
}

async function handleStageChange(appId: string, newStage: string) {
  try {
    await jobService.updateApplicationStage(appId, { stage: newStage })
    await fetchApplications()
  } catch (err: any) {
    alert(err?.detail || '状态变更失败')
  }
}

function openInterviewModal(app: JobApplicationItem) {
  activeApp.value = app
  formInterviewRound.value = app.stage.includes('interview') ? '深入技术面试' : '技术初试'
  showInterviewModal.value = true
}

async function saveInterviewRecord() {
  if (!activeApp.value) return
  try {
    await jobService.addInterviewRecord(activeApp.value.id, {
      round_title: formInterviewRound.value,
      interview_time: formInterviewTime.value,
      interviewer: formInterviewer.value,
      questions_and_feedback: formInterviewFeedback.value
    })
    showInterviewModal.value = false
    await fetchApplications()
  } catch (err: any) {
    alert(err?.detail || '记录保存失败')
  }
}

function openOfferModal(app: JobApplicationItem) {
  activeApp.value = app
  showOfferModal.value = true
}

async function saveOfferRecord() {
  if (!activeApp.value) return
  try {
    await jobService.updateOfferDetails(activeApp.value.id, {
      salary: formOfferSalary.value,
      benefits: formOfferBenefits.value,
      deadline: formOfferDeadline.value,
      status: 'accepted'
    })
    showOfferModal.value = false
    await fetchApplications()
  } catch (err: any) {
    alert(err?.detail || 'Offer 保存失败')
  }
}

async function handleDelete(appId: string) {
  if (!confirm('确定从看板移除该岗位吗？')) return
  try {
    await jobService.deleteApplication(appId)
    await fetchApplications()
  } catch (err: any) {
    alert(err?.detail || '删除失败')
  }
}

onMounted(() => {
  fetchApplications()
})
</script>
