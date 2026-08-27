<template>
  <div class="conversation-shell">
    <aside class="conversation-sidebar">
      <div class="conversation-sidebar-head">
        <div>
          <div class="meta-label !text-slate-500">求职会话管理</div>
          <div class="conversation-title">历史会话</div>
        </div>
      </div>

      <div class="flex w-full gap-2">
        <button class="btn btn-primary flex-1 justify-center" @click="startConversation">新建会话</button>
        <button class="btn btn-secondary flex-1 justify-center" @click="refresh">刷新列表</button>
      </div>

      <SurfaceCard compact>
        <div class="flex items-center justify-between mb-2">
          <label class="meta-label block !text-slate-500">大语言模型</label>
          <span v-if="currentModelInfo" class="text-[11px] font-medium text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
            {{ currentModelInfo.pricingTag || '计费透明' }}
          </span>
        </div>
        
        <div class="relative">
          <select
            :value="chat.selectedModel"
            class="w-full text-xs font-medium text-slate-800 bg-slate-50 border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all cursor-pointer"
            @change="(e: any) => chat.setModel(e.target.value)"
          >
            <optgroup label="🔥 推荐核心模型">
              <option 
                v-for="m in recommendedModels" 
                :key="m.id" 
                :value="m.id"
              >
                {{ m.name }} ({{ m.provider }}) - {{ m.pricingTag }}
              </option>
            </optgroup>
            <optgroup label="⚡ 更多大模型">
              <option 
                v-for="m in otherModels" 
                :key="m.id" 
                :value="m.id"
              >
                {{ m.name }} ({{ m.provider }}) - {{ m.pricingTag }}
              </option>
            </optgroup>
          </select>
        </div>

        <div v-if="currentModelInfo" class="mt-2 text-[11px] text-slate-500 bg-slate-100/70 p-2 rounded-md border border-slate-200/80 leading-relaxed">
          <div class="flex items-center justify-between mb-1">
            <span class="font-semibold text-slate-700">{{ currentModelInfo.name }}</span>
            <span class="text-[10px] px-1.5 py-0.2 bg-blue-100 text-blue-700 rounded font-medium">{{ currentModelInfo.tag || currentModelInfo.provider }}</span>
          </div>
          <div>{{ currentModelInfo.description }}</div>
        </div>

        <label class="meta-label mb-2 mt-4 block !text-slate-500">对话模式</label>
        <div class="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 border border-slate-200">
          <button 
            v-for="opt in [{value: 'auto', label: '自动'}, {value: 'job', label: '求职'}, {value: 'rag', label: '面经'}]" 
            :key="opt.value" 
            type="button"
            :class="['px-1 py-1.5 text-xs font-semibold rounded-md transition-all text-center', chat.mode === opt.value ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-900']"
            @click="chat.setMode(opt.value as any)"
          >
            {{ opt.label }}
          </button>
        </div>
        <KeyValueGrid
          class="mt-4"
          :columns="1"
          :items="[
            { label: '当前模型', value: currentModelInfo?.name || chat.selectedModel || '默认模型' },
            { label: '当前会话', value: chat.currentConversationId || '未创建' },
            { label: '最新 Trace', value: chat.currentTraceId || '等待生成' },
          ]"
        />
      </SurfaceCard>

      <AsyncState
        :loading="loadingConversations"
        :error="chat.errorMessage"
        :empty="!conversations.length"
        empty-title="暂无会话"
        empty-description="发送第一条消息后，会话会显示在这里。"
      >
        <div class="list-stack">
          <button
            v-for="item in conversations"
            :key="item.id"
            class="resource-item text-left"
            :class="{ active: item.id === chat.currentConversationId }"
            @click="select(item.id)"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="resource-title text-slate-800">{{ item.title || '未命名会话' }}</div>
              <button 
                class="text-slate-400 hover:text-red-600 transition-colors p-1" 
                title="删除会话" 
                @click.stop="clearConversation(item.id)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
            <div class="resource-meta">
              <span>{{ item.messageCount ?? 0 }} 条消息</span>
              <span>{{ formatDate(item.updatedAt || item.createdAt) }}</span>
            </div>
          </button>
        </div>
      </AsyncState>
    </aside>

    <main class="conversation-main">
      <div class="message-list flex-1 min-h-[480px]">
        <AsyncState
          :loading="false"
          :empty="!messages.length"
          empty-title="开始与智能求职 Agent 对话"
          empty-description="支持简历诊断、项目 STAR 润色、大厂模拟面试、人岗精准匹配与八股面经知识库问答。"
        >
          <div class="space-y-6">
            <article 
              v-for="(message, index) in messages" 
              :key="index" 
              :class="['flex items-start gap-4', message.role === 'user' ? 'flex-row-reverse' : '']"
            >
              <!-- Avatar -->
              <div :class="['flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg text-sm font-bold border', 
                message.role === 'user' ? 'bg-slate-800 border-slate-700 text-slate-100' : 'bg-blue-50 border-blue-100 text-blue-600']">
                <template v-if="message.role === 'user'">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </template>
                <template v-else>
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </template>
              </div>

              <!-- Message Block -->
              <div :class="['flex-1 min-w-0 flex flex-col', message.role === 'user' ? 'items-end' : 'items-start']">
                <span class="text-xs font-semibold text-zinc-500 mb-1">
                  {{ message.role === 'user' ? '求职者' : 'Ragent 求职助手' }}
                </span>
                
                <!-- Chat Bubble Container -->
                <div 
                  v-if="message.role === 'user'" 
                  class="text-left max-w-[85%]"
                >
                  <div v-if="message.attachments?.length" class="flex flex-wrap gap-1.5 mb-1.5 justify-end">
                    <span 
                      v-for="att in message.attachments" 
                      :key="att.filename" 
                      class="inline-flex items-center gap-1 text-[11px] bg-slate-700 text-slate-100 px-2 py-0.5 rounded-md border border-slate-600 shadow-2xs font-mono"
                    >
                      📎 {{ att.filename }} <span class="text-slate-400">({{ att.char_count }}字)</span>
                    </span>
                  </div>
                  <div class="text-sm text-white bg-blue-600 border border-blue-700 rounded-2xl rounded-tr-none px-4 py-2.5 whitespace-pre-wrap selection:bg-blue-800/30">
                    {{ message.content }}
                  </div>
                </div>
                <div 
                  v-else 
                  class="text-left markdown-body bg-slate-50 border border-slate-200/80 rounded-2xl rounded-tl-none px-4 py-2.5 max-w-[85%] selection:bg-blue-500/10" 
                  v-html="renderMarkdown(message.content || (isLoading && index === messages.length - 1 ? '*AI 正在处理...*' : ''))"
                >
                </div>
              </div>
            </article>
          </div>
        </AsyncState>
      </div>

      <!-- Agent Steps Logs -->
      <SurfaceCard v-if="chat.streamEvents.length" compact class="border-slate-200 bg-slate-50/80">
        <div class="flex items-center justify-between border-b border-slate-200 pb-3">
          <div class="flex items-center gap-2">
            <span class="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span class="text-xs font-semibold text-slate-500">Agent 推理与工具执行动态</span>
          </div>
          <button class="btn btn-secondary !px-2.5 !py-1 text-xs" @click="showDetails = !showDetails">
            {{ showDetails ? '收起明细' : '查看执行明细 (' + chat.streamEvents.length + ')' }}
          </button>
        </div>

        <div v-if="showDetails" class="mt-4 border-l border-slate-200 ml-2 pl-4 space-y-3">
          <article v-for="(event, index) in chat.streamEvents" :key="index" class="relative text-xs">
            <span class="absolute -left-[21px] top-1 flex h-2 w-2 items-center justify-center rounded-full bg-slate-200 ring-4 ring-slate-100">
              <span :class="['h-1.5 w-1.5 rounded-full', event.type === 'error' ? 'bg-red-500' : event.type === 'done' || event.type === 'final_answer' ? 'bg-emerald-500' : 'bg-blue-500']"></span>
            </span>

            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center flex-wrap gap-2">
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                    {{ event.type === 'tool_call' ? '工具调用' : (event.type === 'observation' ? '观察结果' : (event.type === 'react_step' ? '推理思考' : '执行事件')) }}
                  </span>
                  <span v-if="event.tool" class="text-zinc-600 font-mono">工具: {{ event.tool }}</span>
                </div>
                <p class="mt-1 text-slate-600 font-mono">{{ event.thought || event.reason || event.content || event.result?.summary || '执行中' }}</p>
              </div>
            </div>

            <div v-if="event.args || event.result" class="mt-2 space-y-1 bg-white rounded-lg p-2 border border-slate-200 font-mono text-[11px]">
              <DataPreview v-if="event.args" :data="event.args" empty-text="" />
              <DataPreview v-if="event.result" :data="event.result" empty-text="" />
            </div>
          </article>
        </div>
      </SurfaceCard>

      <div 
        class="chat-composer relative"
        @dragover.prevent="isDraggingOver = true"
        @dragleave.prevent="isDraggingOver = false"
        @drop.prevent="handleFileDrop"
      >
        <!-- Drag Over Overlay -->
        <div v-if="isDraggingOver" class="absolute inset-0 z-20 flex items-center justify-center bg-blue-50/90 border-2 border-dashed border-blue-400 rounded-2xl backdrop-blur-xs">
          <div class="text-center">
            <span class="text-2xl">📄</span>
            <p class="mt-1 text-sm font-bold text-blue-700">松开鼠标即可上传并解析文档或图片</p>
            <p class="text-xs text-blue-500">支持 PDF、Word (.docx/.doc)、TXT、Markdown 以及图片/长截图 (PNG/JPG/WEBP)</p>
          </div>
        </div>

        <!-- Attached Files Badges Area -->
        <div v-if="attachedFiles.length > 0" class="mb-2 p-2 bg-blue-50/70 border border-blue-200 rounded-xl flex flex-wrap items-center gap-2">
          <div 
            v-for="(att, idx) in attachedFiles" 
            :key="idx" 
            class="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-blue-200 shadow-2xs text-xs"
          >
            <span 
              class="px-1.5 py-0.5 rounded text-white font-bold text-[10px]"
              :class="['PNG','JPG','JPEG','WEBP','BMP'].includes(att.file_type) ? 'bg-amber-600' : 'bg-blue-600'"
            >
              {{ ['PNG','JPG','JPEG','WEBP','BMP'].includes(att.file_type) ? '🖼️ ' + att.file_type : att.file_type }}
            </span>
            <span class="font-semibold text-slate-800 truncate max-w-[200px]">{{ att.filename }}</span>
            <span class="text-slate-400 text-[11px]">({{ formatFileSize(att.file_size) }} · {{ att.char_count }}字)</span>
            <button 
              type="button" 
              class="text-slate-400 hover:text-red-600 font-bold ml-1 transition-colors" 
              title="移除附件" 
              @click="removeAttachment(idx)"
            >
              ✕
            </button>
          </div>
          <span class="text-[11px] text-blue-600 ml-auto font-medium">📎 已附加 {{ attachedFiles.length }} 个附件</span>
        </div>

        <!-- Quick Job Prompts Chips -->
        <div class="flex items-center gap-1.5 overflow-x-auto pb-2 mb-1 scrollbar-none">
          <!-- 上传文件后的专属推荐 Prompt -->
          <template v-if="attachedFiles.length > 0">
            <button
              v-for="chip in [
                '🎯 帮我深度诊断这份简历并给出多维评分',
                '✨ 提炼简历核心项目经历并按 STAR 法则重构润色',
                '🔍 根据这份简历推荐匹配的目标岗位并分析优势短板',
                '🎤 针对这份简历中的技术栈设计 3 道大厂高频面试真题'
              ]"
              :key="chip"
              type="button"
              class="px-2.5 py-1 text-xs bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 hover:border-blue-400 rounded-lg border border-blue-200 shadow-2xs whitespace-nowrap transition-all cursor-pointer"
              @click="clickChip(chip)"
            >
              {{ chip }}
            </button>
          </template>
          <!-- 常规求职推荐 Prompt -->
          <template v-else>
            <button
              v-for="chip in [
                '🎯 帮我分析岗位JD并计算人岗匹配度',
                '✨ 根据 STAR 法则重构项目经历',
                '💬 生成字节后端 HR 高情商破冰话术',
                '🚀 扮演大厂面试官进行模拟面试出题',
                '📋 帮我生成牛客网申自动填表 Payload'
              ]"
              :key="chip"
              type="button"
              class="px-2.5 py-1 text-xs bg-white text-slate-700 hover:text-blue-600 hover:border-blue-300 rounded-lg border border-slate-200 shadow-2xs whitespace-nowrap transition-all cursor-pointer"
              @click="clickChip(chip)"
            >
              {{ chip }}
            </button>
          </template>
        </div>

        <p v-if="uploadError" class="mb-2 text-xs text-red-600">{{ uploadError }}</p>
        <p v-if="chat.errorMessage" class="mb-2 text-sm text-red-600">{{ chat.errorMessage }}</p>

        <!-- 选定大模型与实时计费提示条 -->
        <div class="flex items-center justify-between mb-2 px-1 max-w-[920px] mx-auto text-xs">
          <div class="flex items-center gap-2 text-slate-600">
            <span class="inline-flex items-center gap-1 font-medium text-slate-700 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-md">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd" />
              </svg>
              <span>{{ currentModelInfo?.name || '大语言模型' }}</span>
              <span class="text-[10px] text-slate-400 font-normal">({{ currentModelInfo?.provider }})</span>
            </span>
            <span v-if="currentModelInfo?.pricingTag" class="text-[11px] text-emerald-700 font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              💰 {{ currentModelInfo.pricingTag }}
            </span>
          </div>
          <div class="text-[11px] text-slate-400">
            可在左侧随时切换推理/通用模型
          </div>
        </div>

        <!-- Form & Toolbar -->
        <form class="!flex items-center gap-2 w-full max-w-[920px] mx-auto border border-slate-300 bg-white/95 shadow-md rounded-2xl p-2" @submit.prevent="submit">
          <!-- 隐藏的文件选择 Input -->
          <input 
            ref="fileInputRef" 
            type="file" 
            class="hidden" 
            accept=".pdf,.docx,.doc,.txt,.md,.markdown,.json,.csv,.png,.jpg,.jpeg,.webp,.bmp" 
            multiple 
            @change="onFileSelected" 
          />

          <!-- 附件上传按钮 -->
          <button 
            type="button" 
            :disabled="uploadingFile || isLoading"
            class="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-xl transition-all shrink-0 flex items-center justify-center disabled:opacity-50" 
            title="上传简历或文档附件 (支持 PDF、Word、TXT、MD、PNG、JPG 图片截图)"
            @click="triggerFileInput"
          >
            <svg v-if="!uploadingFile" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
            <span v-else class="flex h-4 w-4 rounded-full border-2 border-blue-600 border-t-transparent animate-spin"></span>
          </button>

          <textarea
            v-model="question"
            class="flex-1 min-h-[40px] max-h-[160px] resize-none outline-none border-0 bg-transparent text-slate-800 placeholder-slate-400 py-2 px-2 text-sm"
            :placeholder="attachedFiles.length ? '已附加上传文件/图片，输入您的诉求（如：请帮我分析诊断并优化简历）...' : '输入求职诉求，或点击左侧 📎 上传简历/图片/文档，或直接拖拽文件到这里...'"
            rows="1"
            @keydown="handleComposerKeydown"
          />

          <button class="chat-send-button shrink-0" :disabled="isLoading || (!question.trim() && !attachedFiles.length)" type="submit" title="发送">
            {{ isLoading ? '...' : '发送' }}
          </button>
        </form>
        <div class="chat-composer-hint text-slate-400 flex items-center justify-between text-xs mt-1 px-1">
          <span>Enter 发送，Shift + Enter 换行</span>
          <span class="text-slate-400">支持拖拽 PDF、DOCX、TXT、MD、PNG、JPG 图片上传</span>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { uploadChatFile, type ChatAttachment } from '@/services/chatService'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'
import { formatShanghaiDateTime } from '@/utils/date'
import { marked } from 'marked'

const auth = useAuthStore()
const chat = useChatStore()
const question = ref('')
const loadingConversations = ref(false)
const messages = computed(() => chat.messages)
const conversations = computed(() => chat.conversations)
const isLoading = computed(() => chat.isLoading)
const showDetails = ref(false)

const currentModelInfo = computed(() => {
  return chat.availableModels.find((m) => m.id === chat.selectedModel) || chat.availableModels[0]
})

const recommendedModels = computed(() => {
  return chat.availableModels.filter((m) => m.isRecommended)
})

const otherModels = computed(() => {
  return chat.availableModels.filter((m) => !m.isRecommended)
})

// 附件上传与拖拽状态
const fileInputRef = ref<HTMLInputElement | null>(null)
const attachedFiles = ref<ChatAttachment[]>([])
const uploadingFile = ref(false)
const uploadError = ref('')
const isDraggingOver = ref(false)

function triggerFileInput() {
  uploadError.value = ''
  fileInputRef.value?.click()
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

async function handleFiles(files: FileList | File[]) {
  if (!files || !files.length) return
  uploadError.value = ''
  uploadingFile.value = true
  try {
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const result = await uploadChatFile(file)
      attachedFiles.value.push(result)
    }
  } catch (err: any) {
    uploadError.value = err?.message || '文件上传解析失败'
  } finally {
    uploadingFile.value = false
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

async function onFileSelected(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) {
    await handleFiles(target.files)
  }
}

async function handleFileDrop(e: DragEvent) {
  isDraggingOver.value = false
  if (e.dataTransfer?.files) {
    await handleFiles(e.dataTransfer.files)
  }
}

function removeAttachment(index: number) {
  attachedFiles.value.splice(index, 1)
}

function renderMarkdown(content: string) {
  if (!content) return ''
  return marked.parse(content) as string
}

async function refresh() {
  loadingConversations.value = true
  try {
    await chat.loadConversations()
  } finally {
    loadingConversations.value = false
  }
}

function startConversation() {
  question.value = ''
  attachedFiles.value = []
  chat.startConversation()
  showDetails.value = false
}

async function submit() {
  const currentMsg = question.value.trim()
  if (!currentMsg && !attachedFiles.value.length) return

  const effectiveMsg = currentMsg || '请帮我深度分析这份已上传的文档，并给出专业评估与优化建议。'
  const attachmentsToSend = attachedFiles.value.length ? [...attachedFiles.value] : undefined

  question.value = ''
  attachedFiles.value = []
  uploadError.value = ''

  await chat.sendMessage(effectiveMsg, attachmentsToSend)
}

function clickChip(chip: string) {
  question.value = chip
  submit()
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  submit()
}

async function select(id: string) {
  await chat.selectConversation(id)
}

async function clearConversation(id: string) {
  if (!window.confirm('确定清空该会话的对话记录吗？会话本身会保留。')) return
  await chat.clearConversation(id)
  showDetails.value = false
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

onMounted(() => {
  refresh()
  chat.loadModels()
})
</script>
