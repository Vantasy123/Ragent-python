<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center justify-center p-2 rounded-xl bg-indigo-50 text-indigo-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z" />
            </svg>
          </span>
          <h1 class="text-2xl font-bold text-slate-900">AI 模拟面试厅</h1>
        </div>
        <p class="text-slate-500 text-sm mt-1">
          沉浸式多角色大厂模拟面试，涵盖技术八股、项目深挖、系统设计与行为BQ，实时打分并生成五维能力报告。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button class="btn btn-primary flex items-center gap-2 shadow-sm" @click="showStartModal = true">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          开启新一轮模拟面试
        </button>
      </div>
    </div>

    <!-- Active Interview Studio or Past Sessions List -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Left: Session History & Selector -->
      <div class="lg:col-span-4 space-y-4">
        <div class="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm">
          <div class="flex items-center justify-between mb-3 text-xs font-bold text-slate-500 uppercase tracking-wider">
            <span>面试会话历史 ({{ sessions.length }})</span>
            <button class="text-xs text-indigo-600 hover:underline" @click="fetchSessions">刷新</button>
          </div>

          <div v-if="loading" class="py-8 text-center text-slate-400 text-sm">加载中...</div>
          <div v-else-if="!sessions.length" class="py-8 text-center text-slate-400 text-sm">
            暂无面试记录，点击右上角开始第一场模拟对练！
          </div>
          <div v-else class="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
            <div
              v-for="s in sessions"
              :key="s.id"
              :class="['p-4 rounded-xl border transition-all cursor-pointer text-left',
                activeSession?.id === s.id ? 'border-indigo-500 bg-indigo-50/40 shadow-sm ring-1 ring-indigo-500/20' : 'border-slate-200 hover:border-slate-300 bg-white']"
              @click="selectSession(s.id)"
            >
              <div class="flex items-start justify-between">
                <div>
                  <h3 class="font-bold text-slate-900 text-sm">{{ s.targetRole }}</h3>
                  <div class="text-xs text-slate-500 mt-1 flex items-center gap-2">
                    <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                      {{ roleLabel(s.roleType) }}
                    </span>
                    <span>难度: {{ s.difficulty }}</span>
                  </div>
                </div>
                <div class="text-right">
                  <span v-if="s.status === 'completed'" class="text-base font-black text-emerald-600">
                    {{ s.overallScore }}<span class="text-xs font-normal text-slate-400">分</span>
                  </span>
                  <span v-else class="px-2 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-800 rounded-full">
                    进行中
                  </span>
                </div>
              </div>
              <div class="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span>{{ s.roundsCount || 0 }} 轮问答考核</span>
                <span>{{ s.createdAt?.slice(0, 10) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Active Interactive Interview Arena -->
      <div class="lg:col-span-8 space-y-6">
        <div v-if="!activeSession" class="bg-white p-12 rounded-2xl border border-slate-200 text-center text-slate-400">
          请在左侧选择一场模拟面试或点击右上角开启新面试。
        </div>

        <div v-else class="space-y-6">
          <!-- Session Status & Summary Card -->
          <div class="bg-gradient-to-br from-indigo-950 via-slate-900 to-purple-950 text-white p-6 rounded-2xl shadow-sm space-y-4">
            <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <div class="flex items-center gap-2">
                  <span class="px-2 py-0.5 text-xs font-bold rounded-md bg-indigo-500/30 text-indigo-200 border border-indigo-400/30">
                    面试官：{{ roleLabel(activeSession.roleType) }}
                  </span>
                  <h2 class="text-xl font-bold text-white">{{ activeSession.targetRole }}</h2>
                </div>
                <p class="text-xs text-indigo-200 mt-1">
                  难度级别: {{ activeSession.difficulty }} | 当前轮次: {{ activeSession.records?.length || 0 }}
                </p>
              </div>

              <div class="flex items-center gap-2">
                <button
                  v-if="activeSession.status !== 'completed'"
                  class="btn btn-secondary text-xs !bg-white/10 !text-white !border-white/20 hover:!bg-white/20"
                  :disabled="generatingNext"
                  @click="handleNextQuestion"
                >
                  {{ generatingNext ? '出题中...' : '+ 生成下一道提问' }}
                </button>
                <button
                  v-if="activeSession.status !== 'completed'"
                  class="btn btn-primary text-xs !bg-emerald-600 hover:!bg-emerald-700"
                  @click="handleFinishSession"
                >
                  🏁 结束面试并生成复盘报告
                </button>
              </div>
            </div>

            <!-- Dimensions Radar / Scores if completed -->
            <div v-if="activeSession.status === 'completed'" class="pt-3 border-t border-white/10 space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-indigo-300">五维胜任力评测雷达</span>
                <span class="text-xs font-bold text-emerald-400">综合得分: {{ activeSession.overallScore }} 分</span>
              </div>

              <div class="grid grid-cols-5 gap-2 text-center text-xs">
                <div class="bg-white/5 p-2 rounded-xl border border-white/10">
                  <div class="font-bold text-white">{{ activeSession.detailedDimensions?.technical_depth ?? '—' }}</div>
                  <div class="text-[10px] text-indigo-200 mt-0.5">技术深度</div>
                </div>
                <div class="bg-white/5 p-2 rounded-xl border border-white/10">
                  <div class="font-bold text-white">{{ activeSession.detailedDimensions?.logic_structure ?? '—' }}</div>
                  <div class="text-[10px] text-indigo-200 mt-0.5">逻辑结构</div>
                </div>
                <div class="bg-white/5 p-2 rounded-xl border border-white/10">
                  <div class="font-bold text-white">{{ activeSession.detailedDimensions?.communication ?? '—' }}</div>
                  <div class="text-[10px] text-indigo-200 mt-0.5">表达沟通</div>
                </div>
                <div class="bg-white/5 p-2 rounded-xl border border-white/10">
                  <div class="font-bold text-white">{{ activeSession.detailedDimensions?.star_framework ?? '—' }}</div>
                  <div class="text-[10px] text-indigo-200 mt-0.5">STAR框架</div>
                </div>
                <div class="bg-white/5 p-2 rounded-xl border border-white/10">
                  <div class="font-bold text-white">{{ activeSession.detailedDimensions?.culture_fit ?? '—' }}</div>
                  <div class="text-[10px] text-indigo-200 mt-0.5">文化契合</div>
                </div>
              </div>

              <div v-if="activeSession.feedbackSummary" class="bg-indigo-900/40 p-3 rounded-xl text-xs text-indigo-100 border border-indigo-400/20">
                <span class="font-bold text-indigo-300 mr-1">复盘总结：</span>
                {{ activeSession.feedbackSummary }}
              </div>
            </div>
          </div>

          <!-- Q&A Rounds Stream -->
          <div class="space-y-4">
            <div
              v-for="(rec, idx) in (activeSession.records || [])"
              :key="rec.id"
              class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm space-y-3 text-left"
            >
              <!-- Question Header -->
              <div class="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
                <div class="flex items-center gap-2">
                  <span class="px-2 py-0.5 text-xs font-bold bg-indigo-100 text-indigo-800 rounded">
                    第 {{ rec.roundNumber }} 轮
                  </span>
                  <span class="text-xs font-semibold text-slate-500">
                    [{{ questionTypeLabel(rec.questionType) }}]
                  </span>
                </div>
                <div v-if="rec.score > 0" class="text-right">
                  <span class="text-base font-black text-indigo-600">{{ rec.score }} 分</span>
                </div>
              </div>

              <!-- Question Content -->
              <div class="text-sm font-semibold text-slate-900 flex items-start gap-2 bg-indigo-50/50 p-3 rounded-xl border border-indigo-100">
                <span class="text-indigo-600 font-black">Q:</span>
                <span>{{ rec.question }}</span>
              </div>

              <!-- Answer Area (Submitted or Answering) -->
              <div v-if="rec.userAnswer" class="space-y-2">
                <div class="text-xs text-slate-700 bg-slate-50 p-3 rounded-xl border border-slate-200 font-mono whitespace-pre-wrap">
                  <span class="font-bold text-slate-900 block mb-1">我的现场作答：</span>
                  {{ rec.userAnswer }}
                </div>

                <!-- AI Evaluation Feedback -->
                <div v-if="rec.feedback" class="bg-emerald-50/70 border border-emerald-200 p-3.5 rounded-xl text-xs text-emerald-950 space-y-1.5">
                  <div class="font-bold text-emerald-800">💡 面试官点评与得分分析：</div>
                  <p>{{ rec.feedback }}</p>
                  <div v-if="rec.improvementTips?.length" class="mt-2 space-y-0.5">
                    <span class="font-semibold text-emerald-900">提升点：</span>
                    <ul class="list-disc list-inside text-emerald-800">
                      <li v-for="(tip, tIdx) in rec.improvementTips" :key="tIdx">{{ tip }}</li>
                    </ul>
                  </div>
                </div>

                <!-- Reference Model Answer Accordion -->
                <details v-if="rec.modelAnswer" class="text-xs bg-slate-100/70 rounded-xl p-2.5 border border-slate-200">
                  <summary class="font-bold text-slate-700 cursor-pointer">📖 查看大厂满分示范回答 (Model Answer)</summary>
                  <div class="mt-2 text-slate-600 leading-relaxed whitespace-pre-wrap pt-2 border-t border-slate-200 font-mono">
                    {{ rec.modelAnswer }}
                  </div>
                </details>
              </div>

              <!-- Answer Input Box (if not answered yet) -->
              <div v-else class="space-y-2 pt-2">
                <textarea
                  v-model="activeAnswers[rec.id]"
                  rows="4"
                  class="textarea w-full text-xs font-mono"
                  placeholder="请输入你的现场面试回答（建议遵循 STAR 法则或 总-分-总 结构）..."
                ></textarea>
                <div class="flex justify-end">
                  <button
                    class="btn btn-primary text-xs"
                    :disabled="evaluatingId === rec.id || !activeAnswers[rec.id]?.trim()"
                    @click="submitAnswer(rec.id)"
                  >
                    {{ evaluatingId === rec.id ? '面试官严审打分中...' : '提交回答进行大模型评测' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Start Interview Modal -->
    <div v-if="showStartModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div class="bg-white w-full max-w-lg rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        <div class="p-5 border-b border-slate-100 flex items-center justify-between">
          <h3 class="text-base font-bold text-slate-900">🚀 开启新一轮 AI 模拟面试</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="showStartModal = false">✕</button>
        </div>

        <div class="p-6 space-y-4 text-xs">
          <div>
            <label class="block font-bold text-slate-700 mb-1">目标岗位方向</label>
            <input v-model="formTargetRole" type="text" class="input w-full" placeholder="例如：Go/Java 后端开发工程师" />
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">用于本场面试的简历</label>
            <select v-model="formResumeId" class="select w-full" :disabled="!resumes.length">
              <option v-if="!resumes.length" value="">暂无简历，将使用通用问题</option>
              <option v-for="resume in resumes" :key="resume.id" :value="resume.id">
                {{ resume.name }}{{ resume.isDefault ? '（默认）' : '' }}
              </option>
            </select>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">面试官角色设定</label>
            <select v-model="formRoleType" class="select w-full">
              <option value="tech_expert">大厂技术专家（重点考察底层原理、高并发与调优）</option>
              <option value="tech_director">技术总监/架构师（重点考察系统设计与复杂架构决策）</option>
              <option value="hr">资深 HRBP（重点考察沟通协作、自驱力与文化契合）</option>
              <option value="peer">研发骨干同事（考察实操落地与敏捷排障）</option>
            </select>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">考核难度</label>
            <select v-model="formDifficulty" class="select w-full">
              <option value="entry">初级 (校招基础八股 / 基础编码)</option>
              <option value="intermediate">中级 (1-3年实战 / 高并发 / 调优)</option>
              <option value="senior">高级 (3-5年深入 / 分布式架构)</option>
              <option value="expert">专家 (技术深度深水区 / 系统级设计)</option>
            </select>
          </div>
        </div>

        <div class="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
          <button class="btn btn-secondary text-xs" @click="showStartModal = false">取消</button>
          <button class="btn btn-primary text-xs" :disabled="starting" @click="startNewSession">
            {{ starting ? '正在准备面试官与考题...' : '立即进入面试' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { jobService, type MockInterviewSessionItem, type ResumeProfile } from '@/services/jobService'

const loading = ref(false)
const starting = ref(false)
const generatingNext = ref(false)
const evaluatingId = ref<string>('')

const sessions = ref<MockInterviewSessionItem[]>([])
const activeSession = ref<MockInterviewSessionItem | null>(null)
const activeAnswers = reactive<Record<string, string>>({})

const showStartModal = ref(false)
const formTargetRole = ref('后端开发工程师（Go/Java）')
const formRoleType = ref('tech_expert')
const formDifficulty = ref('intermediate')
const resumes = ref<ResumeProfile[]>([])
const formResumeId = ref('')

async function fetchResumes() {
  try {
    const res = await jobService.listResumes()
    resumes.value = res.items || []
    if (!formResumeId.value) {
      formResumeId.value = resumes.value.find((resume) => resume.isDefault)?.id || resumes.value[0]?.id || ''
    }
  } catch (err) {
    console.error(err)
  }
}

async function fetchSessions() {
  loading.value = true
  try {
    const res = await jobService.listInterviewSessions()
    sessions.value = res.items || []
    if (sessions.value.length && !activeSession.value) {
      selectSession(sessions.value[0].id)
    }
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
}

async function selectSession(id: string) {
  try {
    activeSession.value = await jobService.getInterviewSession(id)
  } catch (err) {
    console.error(err)
  }
}

async function startNewSession() {
  starting.value = true
  try {
    const res = await jobService.createInterviewSession({
      target_role: formTargetRole.value,
      role_type: formRoleType.value,
      difficulty: formDifficulty.value,
      resume_id: formResumeId.value || undefined
    })
    showStartModal.value = false
    await fetchSessions()
    if (res.id) {
      selectSession(res.id)
    }
  } catch (err: any) {
    alert(err?.detail || '创建面试会话失败')
  } finally {
    starting.value = false
  }
}

async function submitAnswer(recordId: string) {
  const ans = activeAnswers[recordId]
  if (!ans?.trim()) return
  evaluatingId.value = recordId
  try {
    await jobService.evaluateAnswer(recordId, ans)
    if (activeSession.value) {
      selectSession(activeSession.value.id)
    }
  } catch (err: any) {
    alert(err?.detail || '评估失败')
  } finally {
    evaluatingId.value = ''
  }
}

async function handleNextQuestion() {
  if (!activeSession.value) return
  generatingNext.value = true
  try {
    await jobService.generateNextQuestion(activeSession.value.id)
    selectSession(activeSession.value.id)
  } catch (err: any) {
    alert(err?.detail || '出题失败')
  } finally {
    generatingNext.value = false
  }
}

async function handleFinishSession() {
  if (!activeSession.value) return
  try {
    await jobService.finishInterviewSession(activeSession.value.id)
    selectSession(activeSession.value.id)
    fetchSessions()
  } catch (err: any) {
    alert(err?.detail || '结束面试失败')
  }
}

function roleLabel(role: string) {
  const map: Record<string, string> = {
    tech_expert: '技术专家',
    hr: '资深 HRBP',
    tech_director: '架构师/总监',
    peer: '研发同事'
  }
  return map[role] || '面试官'
}

function questionTypeLabel(type: string) {
  const map: Record<string, string> = {
    technical: '技术八股/底层原理',
    project_deep_dive: '简历项目深挖',
    system_design: '架构与系统设计',
    behavioral: '行为面试 BQ',
    hr: 'HR 综合考察'
  }
  return map[type] || '面试提问'
}

onMounted(() => {
  fetchResumes()
  fetchSessions()
})
</script>
