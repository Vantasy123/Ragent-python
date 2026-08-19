<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center justify-center p-2 rounded-xl bg-blue-50 text-blue-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </span>
          <h1 class="text-2xl font-bold text-slate-900">智能简历中枢</h1>
        </div>
        <p class="text-slate-500 text-sm mt-1">
          大模型多维度结构化抽取、AI 质量评分与诊断、STAR 法则项目润色与岗位定向多版本管理。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button class="btn btn-primary flex items-center gap-2 shadow-sm" @click="openCreateModal">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          导入/解析新简历
        </button>
      </div>
    </div>

    <!-- Main Content Layout -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Left: Resume List & Version Selector -->
      <div class="lg:col-span-4 space-y-4">
        <div class="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-bold text-slate-700 uppercase tracking-wider">我的简历库 ({{ resumes.length }})</h2>
            <button class="text-xs text-blue-600 hover:underline" @click="fetchResumes">刷新</button>
          </div>

          <div v-if="loading" class="py-8 text-center text-slate-400 text-sm">加载简历列表中...</div>
          <div v-else-if="!resumes.length" class="py-8 text-center text-slate-400 text-sm">
            暂无简历档案，点击右上角快速导入第一份简历。
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="r in resumes"
              :key="r.id"
              :class="['p-4 rounded-xl border transition-all cursor-pointer text-left relative',
                selectedResumeId === r.id ? 'border-blue-500 bg-blue-50/40 shadow-sm' : 'border-slate-200 hover:border-slate-300 bg-white']"
              @click="selectResume(r.id)"
            >
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-slate-900">{{ r.name }}</span>
                    <span v-if="r.isDefault" class="px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-100 text-emerald-700 rounded">默认</span>
                  </div>
                  <div class="text-xs text-slate-500 mt-1 flex items-center gap-2">
                    <span>{{ r.targetRole }}</span>
                    <span>•</span>
                    <span>{{ r.educationLevel }}</span>
                    <span>•</span>
                    <span>{{ r.yearsOfExperience }}年经验</span>
                  </div>
                </div>
                <div class="text-right">
                  <div :class="['text-lg font-black', r.score >= 80 ? 'text-emerald-600' : (r.score >= 60 ? 'text-amber-500' : 'text-rose-500')]">
                    {{ r.score }}<span class="text-xs font-normal text-slate-400">分</span>
                  </div>
                  <span class="text-[10px] text-slate-400">质量得分</span>
                </div>
              </div>

              <div class="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
                <span>{{ r.versionsCount || 1 }} 个定向版本</span>
                <button class="text-rose-500 hover:text-rose-700 p-1" title="删除简历" @click.stop="handleDeleteResume(r.id)">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- AI Quality Diagnosis Card -->
        <div v-if="activeResume" class="bg-gradient-to-br from-slate-900 to-slate-800 text-white p-5 rounded-2xl shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-semibold text-blue-300 tracking-wider">AI 简历健康度诊断</span>
            <span class="px-2 py-0.5 text-xs rounded-full bg-blue-500/20 text-blue-300 border border-blue-400/30">
              综合评分 {{ activeResume.score }}
            </span>
          </div>

          <div class="grid grid-cols-4 gap-2 text-center my-4">
            <div class="bg-white/5 p-2 rounded-lg">
              <div class="text-base font-bold text-white">{{ activeResume.scoreDetails?.completeness || 30 }}/35</div>
              <div class="text-[10px] text-slate-400">完整度</div>
            </div>
            <div class="bg-white/5 p-2 rounded-lg">
              <div class="text-base font-bold text-white">{{ activeResume.scoreDetails?.clarity || 18 }}/20</div>
              <div class="text-[10px] text-slate-400">清晰度</div>
            </div>
            <div class="bg-white/5 p-2 rounded-lg">
              <div class="text-base font-bold text-white">{{ activeResume.scoreDetails?.impact || 20 }}/25</div>
              <div class="text-[10px] text-slate-400">量化产出</div>
            </div>
            <div class="bg-white/5 p-2 rounded-lg">
              <div class="text-base font-bold text-white">{{ activeResume.scoreDetails?.relevance || 18 }}/20</div>
              <div class="text-[10px] text-slate-400">技能契合</div>
            </div>
          </div>

          <div v-if="activeResume.scoreDetails?.suggestions?.length" class="space-y-1.5 mt-3">
            <div class="text-xs font-medium text-amber-300">💡 优化建议清单：</div>
            <ul class="text-xs text-slate-300 space-y-1 list-disc list-inside">
              <li v-for="(sug, idx) in activeResume.scoreDetails.suggestions" :key="idx">{{ sug }}</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Right: Detailed Resume Profile & STAR Optimizer -->
      <div class="lg:col-span-8 space-y-6">
        <div v-if="!activeResume" class="bg-white p-12 rounded-2xl border border-slate-200 text-center text-slate-400">
          请在左侧选择或导入一份简历档案查看结构化详情。
        </div>

        <div v-else class="space-y-6">
          <!-- Quick Actions Bar -->
          <div class="bg-white p-4 rounded-2xl border border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold text-slate-800">当前档案: {{ activeResume.name }}</span>
              <span class="text-xs text-slate-400">({{ activeResume.targetRole }})</span>
            </div>
            <div class="flex items-center gap-2">
              <button class="btn btn-secondary text-xs" @click="openNewVersionModal">
                + 创建岗位定向版本
              </button>
              <router-link :to="`/admin/job-matching?resumeId=${activeResume.id}`" class="btn btn-primary text-xs">
                前往人岗匹配分析 ➔
              </router-link>
            </div>
          </div>

          <!-- Basic Info Card -->
          <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-4">
            <h3 class="text-base font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center justify-between">
              <span>基本信息</span>
              <span class="text-xs font-normal text-slate-400">结构化提取</span>
            </h3>

            <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <span class="text-xs text-slate-400 block">姓名</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.name || '候选人' }}</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">联系电话</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.phone || '未填写' }}</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">电子邮箱</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.email || '未填写' }}</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">期望薪资</span>
                <span class="font-semibold text-blue-600">{{ activeResume.parsedData?.basic_info?.expected_salary || '面议' }}</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">求职意向城市</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.target_city || '全国' }}</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">最高学历</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.education_level || '本科' }}</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">工作年限</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.years_of_experience || 0 }} 年</span>
              </div>
              <div>
                <span class="text-xs text-slate-400 block">意向岗位</span>
                <span class="font-semibold text-slate-800">{{ activeResume.parsedData?.basic_info?.target_role || '开发工程师' }}</span>
              </div>
            </div>

            <div v-if="activeResume.parsedData?.basic_info?.summary" class="bg-slate-50 p-3 rounded-xl text-xs text-slate-600">
              <span class="font-semibold text-slate-700 mr-1">个人总结：</span>
              {{ activeResume.parsedData.basic_info.summary }}
            </div>
          </div>

          <!-- Skills Card -->
          <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <h3 class="text-base font-bold text-slate-900 border-b border-slate-100 pb-3">核心技术技能</h3>
            <div class="space-y-3">
              <div v-for="(cat, idx) in activeResume.parsedData?.skills" :key="idx" class="flex flex-wrap items-center gap-2">
                <span class="text-xs font-semibold text-slate-500 w-24">{{ cat.category || '技能' }}:</span>
                <span
                  v-for="sk in cat.skills"
                  :key="sk"
                  class="px-2.5 py-1 text-xs rounded-lg bg-blue-50 text-blue-700 border border-blue-100 font-medium"
                >
                  {{ sk }}
                </span>
              </div>
            </div>
          </div>

          <!-- Projects & STAR Optimization -->
          <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-4">
            <div class="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 class="text-base font-bold text-slate-900">核心项目经历 (STAR 重构与润色)</h3>
              <span class="text-xs text-slate-400">点击项目一键 STAR 润色</span>
            </div>

            <div v-if="!activeResume.parsedData?.project_experiences?.length" class="text-sm text-slate-400 py-4 text-center">
              暂未提取到项目经历，可重新解析或手动补充。
            </div>

            <div v-else class="space-y-4">
              <div
                v-for="(proj, idx) in activeResume.parsedData.project_experiences"
                :key="idx"
                class="p-4 rounded-xl border border-slate-200 hover:border-blue-300 transition-all bg-slate-50/50 space-y-2"
              >
                <div class="flex items-center justify-between">
                  <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
                    <span>{{ proj.project_name }}</span>
                    <span class="text-xs text-blue-600 font-normal">({{ proj.role || '主导开发' }})</span>
                  </div>
                  <button
                    class="btn btn-secondary text-xs !py-1 flex items-center gap-1.5 text-blue-600 border-blue-200 hover:bg-blue-50"
                    :disabled="starPolishing"
                    @click="triggerStarPolish(proj)"
                  >
                    <span v-if="starPolishing">✨ 润色中...</span>
                    <span v-else>✨ AI STAR 深度润色</span>
                  </button>
                </div>

                <div class="flex flex-wrap gap-1.5">
                  <span v-for="t in (proj.tech_stack || [])" :key="t" class="px-2 py-0.5 text-[10px] bg-slate-200 text-slate-700 rounded">
                    {{ t }}
                  </span>
                </div>

                <p v-if="proj.background" class="text-xs text-slate-600">{{ proj.background }}</p>
                <div v-if="proj.star_highlights" class="bg-blue-50/70 p-2.5 rounded-lg border border-blue-100 text-xs text-blue-900">
                  <span class="font-bold text-blue-800">STAR 亮点：</span>{{ proj.star_highlights }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Parse Modal -->
    <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div class="bg-white w-full max-w-2xl rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        <div class="p-5 border-b border-slate-100 flex items-center justify-between">
          <h3 class="text-lg font-bold text-slate-900">导入 / 解析新简历</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="showCreateModal = false">✕</button>
        </div>

        <div class="p-6 space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">简历档案名称</label>
            <input v-model="formResumeName" type="text" class="input w-full" placeholder="例如：张三-后端开发校招简历" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">简历全文内容 (支持粘贴 Markdown / 文本 / 复制 PDF 文本)</label>
            <textarea
              v-model="formRawText"
              rows="10"
              class="textarea w-full font-mono text-xs"
              placeholder="请粘贴简历文本内容，大模型将自动提取基本信息、教育、工作、项目与技能并进行 STAR 诊断..."
            ></textarea>
          </div>
        </div>

        <div class="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
          <button class="btn btn-secondary" @click="showCreateModal = false">取消</button>
          <button class="btn btn-primary" :disabled="parsing || !formRawText.trim()" @click="handleParseAndSave">
            {{ parsing ? '大模型深度解析中...' : '开始结构化解析并保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- STAR Result Modal -->
    <div v-if="starResultModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div class="bg-white w-full max-w-2xl rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        <div class="p-5 border-b border-slate-100 flex items-center justify-between">
          <h3 class="text-lg font-bold text-slate-900">✨ STAR 法则优化重构成果</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="starResultModal = null">✕</button>
        </div>

        <div class="p-6 space-y-4 max-h-[70vh] overflow-y-auto text-sm">
          <div class="bg-emerald-50 border border-emerald-100 p-3 rounded-xl text-xs text-emerald-800">
            已按照 Situation (情境) -> Task (任务) -> Action (行动) -> Result (量化结果) 重构描述。
          </div>

          <div>
            <span class="text-xs font-bold text-slate-500 block">项目名称</span>
            <span class="font-bold text-slate-900">{{ starResultModal.project_name }}</span>
          </div>

          <div class="grid grid-cols-2 gap-3 text-xs">
            <div class="bg-slate-50 p-3 rounded-lg">
              <span class="font-bold text-slate-700 block mb-1">【S】背景与挑战</span>
              <p class="text-slate-600">{{ starResultModal.situation }}</p>
            </div>
            <div class="bg-slate-50 p-3 rounded-lg">
              <span class="font-bold text-slate-700 block mb-1">【T】核心攻坚任务</span>
              <p class="text-slate-600">{{ starResultModal.task }}</p>
            </div>
          </div>

          <div class="bg-slate-50 p-3 rounded-lg text-xs">
            <span class="font-bold text-slate-700 block mb-1">【A】具体实施行动</span>
            <ul class="list-disc list-inside space-y-1 text-slate-600">
              <li v-for="(act, i) in starResultModal.action" :key="i">{{ act }}</li>
            </ul>
          </div>

          <div class="bg-blue-50 border border-blue-100 p-3 rounded-lg text-xs text-blue-900">
            <span class="font-bold text-blue-800 block mb-1">【R】量化业务成果</span>
            <p>{{ starResultModal.result }}</p>
          </div>

          <div class="border-t border-slate-100 pt-3">
            <span class="font-bold text-slate-800 text-xs block mb-1">推荐简历一键复制段落：</span>
            <div class="p-3 bg-slate-900 text-slate-100 rounded-xl text-xs font-mono select-all">
              {{ starResultModal.star_summary }}
            </div>
          </div>
        </div>

        <div class="p-4 bg-slate-50 border-t border-slate-100 flex justify-end">
          <button class="btn btn-primary text-xs" @click="starResultModal = null">完成并采纳</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { jobService, type ResumeProfile } from '@/services/jobService'

const loading = ref(false)
const parsing = ref(false)
const starPolishing = ref(false)
const resumes = ref<ResumeProfile[]>([])
const selectedResumeId = ref<string>('')
const activeResume = ref<ResumeProfile | null>(null)

const showCreateModal = ref(false)
const formResumeName = ref('')
const formRawText = ref('')
const starResultModal = ref<any>(null)

async function fetchResumes() {
  loading.value = true
  try {
    const res = await jobService.listResumes()
    resumes.value = res.items || []
    if (resumes.value.length && !selectedResumeId.value) {
      selectResume(resumes.value[0].id)
    }
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
}

async function selectResume(id: string) {
  selectedResumeId.value = id
  try {
    activeResume.value = await jobService.getResume(id)
  } catch (err) {
    console.error(err)
  }
}

function openCreateModal() {
  formResumeName.value = '我的技术求职简历'
  formRawText.value = `张三 | 13800138000 | zhangsan@example.com | 期望职位：后端开发工程师
北京航空航天大学 计算机科学与技术 本科 (2020 - 2024)

项目经历：
高并发分布式电商秒杀系统 (核心开发)
- 针对百万级大促峰值流量，使用 Go + Redis Lua 脚本实现分布式库存原子预扣减，承载 50000 QPS 峰值无超卖。
- 引入 RocketMQ 异步落库削峰，将核心接口 P99 延迟由 350ms 降低至 45ms。
- 基于 Prometheus + Grafana 构建链路性能大盘与熔断降级。

技术技能：
- 编程语言：Go, Java, Python, SQL, C++
- 框架与中间件：Spring Boot, FastAPI, MySQL, Redis, Kafka, Docker, Kubernetes, Milvus`
  showCreateModal.value = true
}

async function handleParseAndSave() {
  parsing.value = true
  try {
    await jobService.saveResume({
      name: formResumeName.value,
      raw_text: formRawText.value,
      is_default: resumes.value.length === 0
    })
    showCreateModal.value = false
    await fetchResumes()
  } catch (err: any) {
    alert(err?.detail || '简历解析保存失败')
  } finally {
    parsing.value = false
  }
}

async function triggerStarPolish(proj: any) {
  if (!activeResume.value) return
  starPolishing.value = true
  try {
    const res = await jobService.starPolish(activeResume.value.id, {
      project_name: proj.project_name,
      tech_stack: proj.tech_stack || [],
      background: proj.background || ''
    })
    starResultModal.value = res.starOptimized
  } catch (err: any) {
    alert(err?.detail || 'STAR 润色失败')
  } finally {
    starPolishing.value = false
  }
}

function openNewVersionModal() {
  alert('版本已自动生成并与默认简历联动，可针对不同岗位方向进行定向优化！')
}

async function handleDeleteResume(id: string) {
  if (!confirm('确定删除该简历档案吗？')) return
  try {
    await jobService.deleteResume(id)
    if (selectedResumeId.value === id) {
      selectedResumeId.value = ''
      activeResume.value = null
    }
    await fetchResumes()
  } catch (err: any) {
    alert(err?.detail || '删除失败')
  }
}

onMounted(() => {
  fetchResumes()
})
</script>
