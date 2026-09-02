<template>
  <div class="space-y-6">
    <!-- Top Header -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center justify-center p-2 rounded-xl bg-purple-50 text-purple-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </span>
          <h1 class="text-2xl font-bold text-slate-900">岗位检索与人岗匹配中枢</h1>
        </div>
        <p class="text-slate-500 text-sm mt-1">
          多源岗位机会检索、JD 智能结构化解析、全维度人岗精准匹配算法、一键生成高情商 HR 打招呼破冰语与定制求职信。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <!-- 实时采集多平台岗位按钮 -->
        <button
          class="btn bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold flex items-center gap-2 shadow-sm shadow-blue-500/20"
          @click="openSyncModal"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 animate-spin-slow" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          🔄 多平台实时采集同步
        </button>

        <button class="btn btn-secondary flex items-center gap-2" @click="showImportModal = true">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          录入 JD
        </button>
      </div>
    </div>

    <!-- Filter & Search Bar -->
    <div class="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-3 flex-1 min-w-[280px]">
        <div class="relative flex-1 min-w-[200px]">
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索职位名称、公司、技能关键词 (如: 后端, Go, Java, 字节)..."
            class="input w-full pl-9 text-sm"
            @keyup.enter="fetchJobs"
          />
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-slate-400 absolute left-3 top-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <select v-model="selectedCity" class="select text-sm w-28" @change="fetchJobs">
          <option value="全国">城市: 全部</option>
          <option value="北京">北京</option>
          <option value="上海">上海</option>
          <option value="深圳">深圳</option>
          <option value="杭州">杭州</option>
          <option value="广州">广州</option>
          <option value="成都">成都</option>
          <option value="武汉">武汉</option>
        </select>

        <select v-model="selectedType" class="select text-sm w-28" @change="fetchJobs">
          <option value="all">类型: 全部</option>
          <option value="campus">校招/应届</option>
          <option value="social">社招全职</option>
          <option value="intern">日常实习</option>
        </select>

        <select v-model="selectedPlatform" class="select text-sm w-36" @change="fetchJobs">
          <option value="all">渠道: 全部平台</option>
          <option value="boss">💼 BOSS直聘</option>
          <option value="liepin">🎯 猎聘网</option>
          <option value="51job">🏢 前程无忧</option>
          <option value="nowcoder">🎓 牛客招聘</option>
        </select>
      </div>

      <div class="flex items-center gap-2">
        <button class="btn btn-secondary text-sm" @click="fetchJobs">查询</button>
      </div>
    </div>

    <!-- Main 2-Column Layout -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Left: Job Cards List -->
      <div class="lg:col-span-5 space-y-4">
        <div class="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm">
          <div class="flex items-center justify-between mb-3 text-xs font-bold text-slate-500 uppercase tracking-wider">
            <span>推荐岗位列表 ({{ jobs.length }})</span>
            <span class="text-blue-600 cursor-pointer hover:underline" @click="openSyncModal">
              + 实时采集更多
            </span>
          </div>

          <div v-if="loadingJobs" class="py-12 text-center text-slate-400 text-sm">加载岗位列表中...</div>
          <div v-else-if="!jobs.length" class="py-12 text-center text-slate-400 text-sm">
            未检索到匹配的岗位机会，可点击上方「🔄 多平台实时采集同步」一键抓取最新真实岗位。
          </div>
          <div v-else class="space-y-3 max-h-[75vh] overflow-y-auto pr-1">
            <div
              v-for="j in jobs"
              :key="j.id"
              :class="['p-4 rounded-xl border transition-all cursor-pointer text-left',
                selectedJob?.id === j.id ? 'border-purple-500 bg-purple-50/40 shadow-sm ring-1 ring-purple-500/20' : 'border-slate-200 hover:border-slate-300 bg-white']"
              @click="selectJob(j)"
            >
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <span :class="['px-1.5 py-0.5 rounded text-[10px] font-bold', getPlatformBadgeClass(j.sourcePlatform)]">
                      {{ getPlatformLabel(j.sourcePlatform) }}
                    </span>
                    <h3 class="font-bold text-slate-900 text-sm hover:text-purple-600 transition-colors">{{ j.title }}</h3>
                  </div>
                  <div class="text-xs text-slate-600 font-medium mt-1.5 flex items-center gap-2">
                    <span class="font-semibold text-slate-800">{{ j.company }}</span>
                    <span class="text-slate-300">•</span>
                    <span>{{ j.city }}</span>
                    <span class="text-slate-300">•</span>
                    <span>{{ j.experienceReq }}</span>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <span class="text-sm font-bold text-rose-600">
                    {{ j.salaryMin }}-{{ j.salaryMax }} {{ j.salaryUnit }}
                  </span>
                </div>
              </div>

              <div class="flex flex-wrap gap-1 mt-2.5">
                <span v-for="sk in (j.requiredSkills || []).slice(0, 4)" :key="sk" class="px-2 py-0.5 text-[10px] bg-slate-100 text-slate-700 rounded font-medium">
                  {{ sk }}
                </span>
                <span v-if="(j.requiredSkills || []).length > 4" class="text-[10px] text-slate-400 self-center">+{{ j.requiredSkills.length - 4 }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Detailed JD & AI Match Diagnostic Report -->
      <div class="lg:col-span-7 space-y-4">
        <div v-if="!selectedJob" class="bg-white p-12 rounded-2xl border border-slate-200/80 shadow-sm text-center">
          <div class="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center text-2xl mx-auto text-slate-400">
            🎯
          </div>
          <h3 class="text-base font-bold text-slate-800 mt-3">请在左侧选择一个岗位</h3>
          <p class="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
            选择岗位后将自动与您的简历进行全维度精准匹配，并提供破冰文案与优化建议。
          </p>
        </div>

        <div v-else class="space-y-4">
          <!-- Job Detail Header Card -->
          <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-4">
            <div class="flex items-start justify-between">
              <div>
                <div class="flex items-center gap-2">
                  <span :class="['px-2 py-0.5 rounded text-xs font-bold', getPlatformBadgeClass(selectedJob.sourcePlatform)]">
                    {{ getPlatformLabel(selectedJob.sourcePlatform) }}
                  </span>
                  <h2 class="text-xl font-bold text-slate-900">{{ selectedJob.title }}</h2>
                </div>
                <div class="flex items-center gap-3 text-sm text-slate-600 mt-2">
                  <span class="font-bold text-slate-900">{{ selectedJob.company }}</span>
                  <span class="text-slate-300">•</span>
                  <span>{{ selectedJob.city }}</span>
                  <span class="text-slate-300">•</span>
                  <span>{{ selectedJob.educationReq }}</span>
                  <span class="text-slate-300">•</span>
                  <span>{{ selectedJob.experienceReq }}</span>
                </div>
              </div>
              <div class="text-right">
                <div class="text-xl font-extrabold text-rose-600">
                  {{ selectedJob.salaryMin }}-{{ selectedJob.salaryMax }} {{ selectedJob.salaryUnit }}
                </div>
                <span class="text-xs text-slate-400 capitalize">{{ selectedJob.jobType === 'campus' ? '校园招聘' : '社会招聘' }}</span>
              </div>
            </div>

            <!-- Tags -->
            <div class="flex flex-wrap gap-1.5">
              <span v-for="tag in selectedJob.companyTags || []" :key="tag" class="px-2.5 py-1 text-xs bg-purple-50 text-purple-700 font-medium rounded-lg">
                {{ tag }}
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span :class="[
                'px-2 py-1 rounded-lg border font-medium',
                selectedJob.detailStatus === 'success'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : selectedJob.detailStatus === 'failed'
                    ? 'bg-rose-50 text-rose-700 border-rose-200'
                    : selectedJob.detailStatus === 'skipped'
                      ? 'bg-slate-50 text-slate-600 border-slate-200'
                      : 'bg-amber-50 text-amber-700 border-amber-200'
              ]">
                {{ selectedJob.detailStatus === 'success' ? '真实详情已采集' : selectedJob.detailStatus === 'failed' ? '详情采集失败，已保留列表岗位' : selectedJob.detailStatus === 'skipped' ? '详情采集已跳过' : '详情尚未采集' }}
              </span>
              <span v-if="selectedJob.detailError" class="text-slate-500 truncate max-w-full" :title="selectedJob.detailError">
                {{ selectedJob.detailError }}
              </span>
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center justify-between pt-2 border-t border-slate-100">
              <div class="flex items-center gap-2">
                <label class="text-xs font-bold text-slate-500">用于匹配诊断的简历:</label>
                <select v-model="targetResumeId" class="select text-xs py-1 h-8 max-w-[200px]" @change="runMatchAnalysis">
                  <option v-for="r in resumes" :key="r.id" :value="r.id">
                    {{ r.name }} ({{ r.targetRole || '通用' }})
                  </option>
                </select>
              </div>

              <div class="flex items-center gap-2">
                <a
                  v-if="selectedJob.sourceUrl"
                  :href="selectedJob.sourceUrl"
                  target="_blank"
                  class="btn btn-secondary text-xs"
                >
                  🔗 打开原招聘页
                </a>
                <button class="btn btn-primary text-xs flex items-center gap-1.5" @click="handleAddToKanban">
                  <span>➕</span>
                  <span>加入投递看板</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Matching Score Report -->
          <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-4">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-lg font-bold text-slate-900">🤖 AI 人岗深度匹配诊断</span>
                <span v-if="matchReport" :class="['px-2 py-0.5 text-xs font-bold rounded-full', matchReport.overallScore >= 80 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200']">
                  {{ matchReport.matchLevel }}
                </span>
              </div>
              <button
                class="btn btn-secondary text-xs"
                :disabled="analyzingMatch"
                @click="runMatchAnalysis"
              >
                {{ analyzingMatch ? '正在深度分析中...' : '重新评估匹配' }}
              </button>
            </div>

            <div v-if="analyzingMatch" class="py-10 text-center text-slate-500 text-sm">
              <div class="animate-spin text-2xl mb-2">⚡</div>
              大模型正在对比简历技能与岗位 JD 核心诉求...
            </div>

            <div v-else-if="matchReport" class="space-y-4">
              <!-- Score Grid -->
              <div class="grid grid-cols-4 gap-3">
                <div class="p-3 bg-purple-50/60 rounded-xl text-center border border-purple-100">
                  <div class="text-xs text-purple-700 font-medium">综合匹配度</div>
                  <div class="text-2xl font-black text-purple-700 mt-0.5">{{ matchReport.overallScore }}%</div>
                </div>
                <div class="p-3 bg-blue-50/60 rounded-xl text-center border border-blue-100">
                  <div class="text-xs text-blue-700 font-medium">技能契合</div>
                  <div class="text-2xl font-black text-blue-700 mt-0.5">{{ matchReport.skillMatchScore }}%</div>
                </div>
                <div class="p-3 bg-emerald-50/60 rounded-xl text-center border border-emerald-100">
                  <div class="text-xs text-emerald-700 font-medium">经历匹配</div>
                  <div class="text-2xl font-black text-emerald-700 mt-0.5">{{ matchReport.experienceMatchScore }}%</div>
                </div>
                <div class="p-3 bg-indigo-50/60 rounded-xl text-center border border-indigo-100">
                  <div class="text-xs text-indigo-700 font-medium">学历资质</div>
                  <div class="text-2xl font-black text-indigo-700 mt-0.5">{{ matchReport.educationMatchScore }}%</div>
                </div>
              </div>

              <!-- Strong & Missing Skills -->
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div class="p-4 bg-emerald-50/40 rounded-xl border border-emerald-100 space-y-2">
                  <div class="font-bold text-emerald-800 flex items-center gap-1">
                    <span>✅ 匹配上的核心优势与亮点</span>
                  </div>
                  <ul class="list-disc list-inside space-y-1 text-slate-700">
                    <li v-for="pt in matchReport.strongPoints" :key="pt">{{ pt }}</li>
                  </ul>
                </div>
                <div class="p-4 bg-rose-50/40 rounded-xl border border-rose-100 space-y-2">
                  <div class="font-bold text-rose-800 flex items-center gap-1">
                    <span>⚠️ 技能缺失与潜在短板</span>
                  </div>
                  <ul class="list-disc list-inside space-y-1 text-slate-700">
                    <li v-for="pt in matchReport.weakPoints" :key="pt">{{ pt }}</li>
                  </ul>
                </div>
              </div>

              <!-- High-EQ Greeting & Cover Letter -->
              <div class="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-slate-800 text-xs flex items-center gap-1">
                    <span>💬 高情商 HR 破冰打招呼文案</span>
                  </span>
                  <button class="text-xs text-blue-600 font-semibold hover:underline" @click="copyText(matchReport.customizedGreeting)">
                    复制文案
                  </button>
                </div>
                <p class="text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200/60 leading-relaxed whitespace-pre-wrap">
                  {{ matchReport.customizedGreeting }}
                </p>
              </div>
            </div>
          </div>

          <!-- Raw JD Text -->
          <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <h3 class="text-sm font-bold text-slate-900">原始岗位 JD 描述</h3>
            <div class="p-4 bg-slate-50 rounded-xl text-xs text-slate-700 leading-relaxed whitespace-pre-wrap border border-slate-100 max-h-60 overflow-y-auto">
              {{ selectedJob.jdText || '暂无详细 JD 内容' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 多平台实时采集同步模态框 -->
    <div v-if="showSyncModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
      <div class="bg-white rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl border border-slate-200">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div class="flex items-center gap-2">
            <span class="text-xl">🔄</span>
            <h3 class="text-lg font-bold text-slate-900">多招聘平台岗位实时采集与同步</h3>
          </div>
          <button class="text-slate-400 hover:text-slate-600 text-xl font-bold cursor-pointer" @click="showSyncModal = false">
            ✕
          </button>
        </div>

        <!-- CDP 浏览器连接状态与指引卡片 -->
        <div :class="['p-3.5 rounded-xl border text-xs leading-relaxed space-y-2', cdpConnected ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900' : 'bg-amber-50/80 border-amber-200 text-amber-900']">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 font-bold">
              <span class="flex h-2.5 w-2.5 rounded-full" :class="cdpConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'"></span>
              <span>{{ cdpConnected ? 'Chrome CDP 真实浏览器：已连接 (端口 9223)' : 'Chrome CDP 调试端口未连接' }}</span>
            </div>
            <button class="text-xs text-blue-600 hover:underline font-medium" @click="detectCdpStatus">
              🔄 重新探测
            </button>
          </div>

          <div v-if="cdpConnected" class="text-[11px] text-emerald-700">
            已连接本地 Chrome 调试端口，活动标签页 {{ cdpTabsCount }} 个。登录态和平台页面可用性会在实际采集时进一步校验。
          </div>
          <div v-else-if="cdpError" class="text-[11px] text-amber-800">
            {{ cdpError }}
          </div>
          <div v-else class="space-y-1.5 text-[11px] text-amber-800">
            <p>为 100% 绕过反爬与风控，请在 PowerShell 中运行以下命令启动 Chrome：</p>
            <div class="bg-white/80 p-1.5 rounded border border-amber-300 font-mono text-[10px] text-slate-800 flex items-center justify-between gap-2">
              <span class="truncate select-all">& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --user-data-dir="C:\ragent-chrome"</span>
              <button class="text-blue-600 font-bold shrink-0 hover:underline" @click="copyText('& \x22C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\x22 --remote-debugging-port=9223 --user-data-dir=\x22C:\\ragent-chrome\x22')">
                复制
              </button>
            </div>
            <p class="text-amber-600">未启动时将自动尝试使用后台 Playwright 独立浏览器驱动进行页面抓取。</p>
          </div>
        </div>

        <div class="space-y-4">
          <!-- 目标渠道选择 -->
          <div>
            <label class="meta-label mb-2 block font-bold">选择采集渠道</label>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="p in syncPlatforms"
                :key="p.id"
                type="button"
                :class="[
                  'p-2.5 rounded-xl border text-xs font-semibold flex items-center gap-2 transition-all text-left',
                  syncTargetPlatform === p.id
                    ? 'border-blue-600 bg-blue-50/60 text-blue-700 ring-1 ring-blue-500/20'
                    : 'border-slate-200 hover:border-slate-300 text-slate-700 bg-white'
                ]"
                @click="syncTargetPlatform = p.id"
              >
                <span>{{ p.icon }}</span>
                <div>
                  <div>{{ p.name }}</div>
                  <div class="text-[10px] text-slate-400 font-normal">{{ p.mode }}</div>
                </div>
              </button>
            </div>
          </div>

          <!-- 关键词与城市 -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="meta-label mb-1.5 block font-bold">职位关键词</label>
              <input
                v-model="syncKeyword"
                type="text"
                placeholder="如: Java, Python, 大模型, 前端"
                class="input text-sm"
              />
            </div>
            <div>
              <label class="meta-label mb-1.5 block font-bold">目标城市</label>
              <select v-model="syncCity" class="select text-sm w-full">
                <option value="全国">全国 (主流大厂)</option>
                <option value="北京">北京</option>
                <option value="上海">上海</option>
                <option value="深圳">深圳</option>
                <option value="杭州">杭州</option>
                <option value="广州">广州</option>
                <option value="成都">成都</option>
                <option value="武汉">武汉</option>
              </select>
            </div>
          </div>

          <!-- 快速关键词预设 -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="text-[11px] text-slate-400 font-medium">热门预设:</span>
            <button
              v-for="kw in ['Java后端', 'Python大模型', 'Go架构师', '前端开发', 'AI Agent算法', '全栈开发']"
              :key="kw"
              type="button"
              class="px-2 py-0.5 rounded-md text-[11px] bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 transition-colors"
              @click="syncKeyword = kw"
            >
              {{ kw }}
            </button>
          </div>

          <!-- 抓取上限 -->
          <div class="flex items-center justify-between text-xs text-slate-600 pt-2 border-t border-slate-100">
            <span>每个平台采集条数:</span>
            <div class="flex items-center gap-2">
              <button
                v-for="cnt in [5, 10, 15]"
                :key="cnt"
                type="button"
                :class="['px-2.5 py-1 rounded-lg font-bold text-xs', syncLimit === cnt ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600']"
                @click="syncLimit = cnt"
              >
                {{ cnt }} 条
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between text-xs text-slate-600 pt-2 border-t border-slate-100">
            <span>分页采集页数:</span>
            <select v-model.number="syncMaxPages" class="select text-xs py-1 h-8 w-24">
              <option :value="1">1 页</option>
              <option :value="2">2 页</option>
              <option :value="5">5 页</option>
              <option :value="10">10 页</option>
            </select>
          </div>

          <label class="flex items-start gap-2.5 rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs text-slate-700 cursor-pointer">
            <input v-model="enrichDetails" type="checkbox" class="mt-0.5 accent-blue-600" />
            <span>
              <span class="font-bold text-slate-800">同步后采集真实详情页</span>
              <span class="block mt-0.5 text-[11px] text-slate-500">补全完整 JD、技能、职责和福利；详情失败时仍保留列表岗位。</span>
            </span>
          </label>

          <!-- 同步状态提示 -->
          <div v-if="syncMessage" :class="['p-3 rounded-xl text-xs leading-relaxed', syncError ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-emerald-50 text-emerald-800 border border-emerald-200']">
            {{ syncMessage }}
          </div>
        </div>

        <div class="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
          <button class="btn btn-secondary text-sm" :disabled="syncing || liveSearching" @click="showSyncModal = false">
            取消
          </button>
          <button
            class="btn btn-secondary text-sm flex items-center gap-2"
            :disabled="syncing || liveSearching || !syncKeyword.trim()"
            @click="handleLiveSearch"
          >
            <span v-if="liveSearching" class="animate-spin">⚡</span>
            <span>{{ liveSearching ? '正在实时直搜...' : '实时直搜（不入库）' }}</span>
          </button>
          <button
            class="btn btn-primary text-sm flex items-center gap-2"
            :disabled="syncing || liveSearching || !syncKeyword.trim()"
            @click="handleStartSync"
          >
            <span v-if="syncing" class="animate-spin">⚡</span>
            <span>{{ syncing ? '正在真实浏览器采集同步中...' : '开始真实采集' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 录入 JD 模态框 -->
    <div v-if="showImportModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
      <div class="bg-white rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-xl border border-slate-200">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 class="text-lg font-bold text-slate-900">录入 / 导入目标岗位 JD</h3>
          <button class="text-slate-400 hover:text-slate-600 text-xl font-bold cursor-pointer" @click="showImportModal = false">
            ✕
          </button>
        </div>

        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="meta-label mb-1 block">岗位名称</label>
              <input v-model="formJobTitle" placeholder="如: 后端开发专家" class="input text-sm" />
            </div>
            <div>
              <label class="meta-label mb-1 block">招聘公司</label>
              <input v-model="formJobCompany" placeholder="如: 腾讯 / 阿里 / 美团" class="input text-sm" />
            </div>
          </div>

          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="meta-label mb-1 block">工作城市</label>
              <input v-model="formJobCity" placeholder="北京" class="input text-sm" />
            </div>
            <div>
              <label class="meta-label mb-1 block">底薪 (K)</label>
              <input v-model.number="formJobMinSalary" type="number" class="input text-sm" />
            </div>
            <div>
              <label class="meta-label mb-1 block">顶薪 (K)</label>
              <input v-model.number="formJobMaxSalary" type="number" class="input text-sm" />
            </div>
          </div>

          <div>
            <label class="meta-label mb-1 block">原始 JD 文本</label>
            <textarea
              v-model="formJobJdText"
              rows="6"
              placeholder="在此粘贴招聘网站的原始职位描述与任职资格要求，系统将自动使用大模型提取技能栈..."
              class="textarea text-xs"
            ></textarea>
          </div>
        </div>

        <div class="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
          <button class="btn btn-secondary text-sm" @click="showImportModal = false">取消</button>
          <button
            class="btn btn-primary text-sm"
            :disabled="importing || !formJobTitle.trim() || !formJobCompany.trim()"
            @click="handleImportJob"
          >
            {{ importing ? '正在智能解析并录入...' : '确定录入' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { jobService, type JobOpportunity, type JobMatchReport, type ResumeProfile } from '@/services/jobService'

const route = useRoute()

const jobs = ref<JobOpportunity[]>([])
const loadingJobs = ref(false)
const selectedJob = ref<JobOpportunity | null>(null)

const resumes = ref<ResumeProfile[]>([])
const targetResumeId = ref('')

const searchKeyword = ref('')
const selectedCity = ref('全国')
const selectedType = ref('all')
const selectedPlatform = ref('all')

const matchReport = ref<JobMatchReport | null>(null)
const analyzingMatch = ref(false)
let matchRequestToken = 0

const showImportModal = ref(false)
const importing = ref(false)
const formJobTitle = ref('')
const formJobCompany = ref('')
const formJobCity = ref('北京')
const formJobMinSalary = ref(25)
const formJobMaxSalary = ref(45)
const formJobJdText = ref('')

// 多平台实时采集同步状态
const showSyncModal = ref(false)
const syncing = ref(false)
const liveSearching = ref(false)
const syncTargetPlatform = ref('all')
const syncKeyword = ref('后端开发')
const syncCity = ref('全国')
const syncLimit = ref(10)
const syncMaxPages = ref(1)
const enrichDetails = ref(false)
const syncMessage = ref('')
const syncError = ref(false)
const cdpConnected = ref(false)
const cdpTabsCount = ref(0)
const cdpError = ref('')

const syncPlatforms = [
  { id: 'all', name: '全部平台聚合', mode: '多源真实并发采集', icon: '🌐' },
  { id: 'boss', name: 'BOSS 直聘', mode: 'Chrome CDP 真实驱动', icon: '💼' },
  { id: 'liepin', name: '猎聘网', mode: 'Chrome CDP 真实驱动', icon: '🎯' },
  { id: '51job', name: '前程无忧', mode: 'Chrome CDP 真实驱动', icon: '🏢' },
  { id: 'nowcoder', name: '牛客招聘', mode: 'Chrome CDP 真实驱动', icon: '🎓' },
]

async function detectCdpStatus() {
  try {
    const res = await jobService.getCdpStatus()
    const data = res?.data || {}
    cdpConnected.value = Boolean(data.connected)
    cdpTabsCount.value = Number(data.tabs_count || 0)
    const detectedPlatforms = data.logged_in_platforms || []
    const unresolved = syncPlatforms
      .filter((platform) => platform.id !== 'all' && !detectedPlatforms.includes(platform.id))
      .map((platform) => platform.name)
    cdpError.value = data.error || (unresolved.length ? `未检测到平台标签页：${unresolved.join('、')}；标签页存在也不等于已登录。` : '')
  } catch (err: any) {
    cdpConnected.value = false
    cdpTabsCount.value = 0
    cdpError.value = err?.detail || err?.message || 'CDP 状态探测失败，请先登录应用后重试。'
  }
}

function getPlatformLabel(plat: string) {
  switch (plat) {
    case 'boss': return 'BOSS直聘'
    case 'liepin': return '猎聘网'
    case '51job': return '前程无忧'
    case 'nowcoder': return '牛客招聘'
    default: return '招聘平台'
  }
}

function getPlatformBadgeClass(plat: string) {
  switch (plat) {
    case 'boss': return 'bg-cyan-50 text-cyan-700 border border-cyan-200'
    case 'liepin': return 'bg-amber-50 text-amber-700 border border-amber-200'
    case '51job': return 'bg-emerald-50 text-emerald-700 border border-emerald-200'
    case 'nowcoder': return 'bg-blue-50 text-blue-700 border border-blue-200'
    default: return 'bg-slate-100 text-slate-700'
  }
}

async function fetchJobs() {
  loadingJobs.value = true
  try {
    const res = await jobService.listPostings({
      keyword: searchKeyword.value.trim() || undefined,
      city: selectedCity.value !== '全国' ? selectedCity.value : undefined,
      job_type: selectedType.value !== 'all' ? selectedType.value : undefined,
      source_platform: selectedPlatform.value !== 'all' ? selectedPlatform.value : undefined,
      limit: 50
    })
    jobs.value = res.items || []
    if (!jobs.value.length) {
      selectedJob.value = null
      matchReport.value = null
      matchRequestToken += 1
    } else if (!selectedJob.value || !jobs.value.some(j => j.id === selectedJob.value?.id)) {
      selectJob(jobs.value[0])
    }
  } catch (err) {
    console.error(err)
  } finally {
    loadingJobs.value = false
  }
}

async function fetchResumes() {
  try {
    const res = await jobService.listResumes()
    resumes.value = res.items || []
    if (resumes.value.length) {
      const defaultOne = resumes.value.find(r => r.isDefault) || resumes.value[0]
      targetResumeId.value = (route.query.resumeId as string) || defaultOne.id
    }
  } catch (err) {
    console.error(err)
  }
}

function selectJob(job: JobOpportunity) {
  selectedJob.value = job
  matchReport.value = null
  if (targetResumeId.value) {
    runMatchAnalysis()
  }
}

async function runMatchAnalysis() {
  if (!selectedJob.value || !targetResumeId.value) return
  const token = ++matchRequestToken
  const jobId = selectedJob.value.id
  const resumeId = targetResumeId.value
  analyzingMatch.value = true
  try {
    const report = await jobService.analyzeMatch(resumeId, jobId)
    if (token === matchRequestToken && selectedJob.value?.id === jobId && targetResumeId.value === resumeId) {
      matchReport.value = report
    }
  } catch (err) {
    if (token === matchRequestToken) console.error(err)
  } finally {
    if (token === matchRequestToken) analyzingMatch.value = false
  }
}

async function openSyncModal() {
  syncMessage.value = ''
  syncError.value = false
  showSyncModal.value = true
  await detectCdpStatus()
}

function formatPlatformErrors(errors: Record<string, any>) {
  const entries = Object.entries(errors || {})
  if (!entries.length) return ''

  return entries.map(([platform, value]) => {
    const detail = typeof value === 'string' ? { message: value } : (value || {})
    const label = getPlatformLabel(platform)
    switch (detail.reason_code) {
      case 'auth_required':
      case 'auth_unverified':
        return `${label}：请在 Ragent 专用 Chrome 窗口完成登录后重新抓取，系统不会保存平台密码。`
      case 'anti_bot':
        return `${label}：页面触发安全验证，请在 Ragent 专用 Chrome 窗口完成人工验证后重新抓取。`
      case 'cdp_unavailable':
        return `${label}：未连接 Ragent Chrome CDP，请启动 9223 调试端口后重试。`
      case 'navigation_blocked':
        return `${label}：页面导航被拦截，请先在 Ragent Chrome 窗口打开并完成平台页面验证后重试。`
      case 'dom_missing':
        return `${label}：未识别到岗位列表，请刷新平台页面后重试。`
      default:
        return `${label}：${detail.message || '真实页面采集失败，请在浏览器中检查登录和页面状态。'}`
    }
  }).join('；')
}

async function handleLiveSearch() {
  liveSearching.value = true
  syncMessage.value = ''
  syncError.value = false
  try {
    const res = await jobService.liveSearchJobs({
      platform: syncTargetPlatform.value,
      keyword: syncKeyword.value.trim(),
      city: syncCity.value,
      limit_per_platform: syncLimit.value,
      mode: 'auto'
    })
    const data = res?.data || { jobs: [], total: 0, persisted: false }
    if (data.persisted !== false) {
      throw new Error('实时直搜接口返回了异常的持久化状态')
    }
    jobs.value = data.jobs || []
    selectedJob.value = jobs.value[0] || null
    matchReport.value = null
    matchRequestToken += 1
    if (jobs.value.length) {
      syncMessage.value = `🔎 已返回 ${data.total || jobs.value.length} 条实时岗位，未写入本地岗位库。`
      if (selectedJob.value && targetResumeId.value) runMatchAnalysis()
    } else {
      const errors = formatPlatformErrors(data.platform_errors || {})
      syncError.value = Boolean(errors)
      syncMessage.value = errors ? `⚠️ 实时直搜未完成：${errors}` : '未抓取到符合条件的真实在招岗位。'
    }
  } catch (err: any) {
    syncError.value = true
    syncMessage.value = `实时直搜失败: ${err?.detail || err?.message || '网络或接口超时'}`
  } finally {
    liveSearching.value = false
  }
}

async function handleStartSync() {
  syncing.value = true
  syncMessage.value = ''
  syncError.value = false

  try {
    const res = await jobService.syncJobs({
      platform: syncTargetPlatform.value,
      keyword: syncKeyword.value.trim(),
      city: syncCity.value,
      limit_per_platform: syncLimit.value,
      max_pages: syncMaxPages.value,
      enrich_details: enrichDetails.value,
      mode: 'auto'
    })

    const stats = res?.data?.stats || {}
    const detailSummary = enrichDetails.value
      ? `，详情成功 ${stats.detail_succeeded || 0}、失败 ${stats.detail_failed || 0}、跳过 ${stats.detail_skipped || 0}`
      : ''
    if (stats.total_fetched > 0) {
      syncMessage.value = `🎉 ${res?.message || '真实采集同步完成！'} (总抓取 ${stats.total_fetched || 0} 条真实岗位，新增入库 ${stats.created || 0} 条，更新 ${stats.updated || 0} 条${detailSummary})`
    } else {
      const errors = stats.platform_errors || {}
      const errList = formatPlatformErrors(stats.platform_errors || {})
      if (errList) {
        syncError.value = true
        syncMessage.value = `⚠️ 采集未获取到数据：${errList}。请确认 Chrome 9223 端口、平台登录态和页面验证码状态。`
      } else {
        syncMessage.value = '未抓取到符合条件的真实在招岗位。'
      }
    }

    // 重新拉取岗位并选中最新一条
    await fetchJobs()
    if (jobs.value.length) {
      selectJob(jobs.value[0])
    }
  } catch (err: any) {
    syncError.value = true
    syncMessage.value = `同步失败: ${err?.detail || err?.message || '网络或接口超时'}`
  } finally {
    syncing.value = false
  }
}

async function handleImportJob() {
  importing.value = true
  try {
    await jobService.createPosting({
      title: formJobTitle.value,
      company: formJobCompany.value,
      city: formJobCity.value,
      salary_min: formJobMinSalary.value,
      salary_max: formJobMaxSalary.value,
      jd_text: formJobJdText.value
    })
    showImportModal.value = false
    formJobJdText.value = ''
    await fetchJobs()
  } catch (err: any) {
    alert(err?.detail || '录入失败')
  } finally {
    importing.value = false
  }
}

async function handleAddToKanban() {
  if (!selectedJob.value) return
  try {
    await jobService.createApplication({
      job_id: selectedJob.value.id,
      resume_id: targetResumeId.value || undefined,
      stage: 'wishlist',
      apply_channel: selectedJob.value.sourcePlatform === 'nowcoder' ? '牛客网申' : selectedJob.value.sourcePlatform
    })
    alert('已成功将该岗位加入求职看板！')
  } catch (err: any) {
    alert(err?.detail || '加入看板失败')
  }
}

function copyText(text: string) {
  if (!text) return
  navigator.clipboard.writeText(text)
  alert('已复制到剪贴板！')
}

onMounted(async () => {
  await fetchResumes()
  await fetchJobs()
})
</script>
