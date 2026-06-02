<template>
  <section>
    <PageHeader
      title="用户管理"
      eyebrow="访问控制"
      description="管理后台账号、角色和启停状态，同时支持当前登录账号修改密码。"
    >
      <template #actions>
        <div class="inline-actions">
          <button class="btn btn-secondary" @click="load">刷新</button>
          <button class="btn btn-primary" @click="resetForm">新建用户</button>
        </div>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="用户列表" subtitle="查看全部账号，并对单个账号执行编辑或删除。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!users.length"
          empty-title="暂无用户"
          empty-description="至少保留一个管理员账号以保证后台可管理。"
        >
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>用户</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="user in users"
                  :key="user.id"
                  :class="{ 'row-active': selectedUser?.id === user.id }"
                  @click="selectUser(user)"
                >
                  <td>
                    <div class="font-semibold">{{ user.nickname || user.username }}</div>
                    <div class="muted mt-1 text-xs">{{ user.username }}</div>
                  </td>
                  <td>{{ formatRole(user.role) }}</td>
                  <td>
                    <span :class="user.isActive ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                      {{ user.isActive ? '已启用' : '已停用' }}
                    </span>
                  </td>
                  <td>
                    <div class="inline-actions">
                      <button class="btn btn-secondary" @click.stop="edit(user)">编辑</button>
                      <button class="btn btn-danger" @click.stop="remove(user.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="pagination.total" :page-size="pagination.pageSize" :current-page="pagination.pageNo" @update:page="changePage" />
        </AsyncState>
      </SurfaceCard>

      <div class="list-stack">
        <SurfaceCard title="用户表单" subtitle="创建新用户或编辑已有账号的昵称、角色和状态。">
          <div class="form-grid">
            <input v-model="form.username" class="input" :disabled="!!form.id" placeholder="用户名" />
            <input v-model="form.nickname" class="input" placeholder="显示名称" />
            <select v-model="form.role" class="select">
              <option value="admin">管理员</option>
              <option value="user">普通用户</option>
            </select>
            <input
              v-model="form.password"
              type="password"
              class="input"
              :placeholder="form.id ? '如需重置密码，请直接填写新密码' : '初始密码'"
            />
            <label class="inline-actions items-center rounded-2xl border border-slate-200 px-4 py-3">
              <input v-model="form.isActive" type="checkbox" />
              <span>启用用户</span>
            </label>
            <div class="inline-actions">
              <button class="btn btn-primary" :disabled="!form.username.trim() || (!form.id && !form.password.trim())" @click="submit">
                {{ form.id ? '保存用户' : '创建用户' }}
              </button>
              <button v-if="form.id" class="btn btn-secondary" @click="resetForm">取消编辑</button>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard title="当前账号密码" subtitle="该接口只作用于当前登录用户，不支持替他人改密。">
          <div class="form-grid">
            <input v-model="passwordForm.password" type="password" class="input" placeholder="输入新密码" />
            <button class="btn btn-primary" :disabled="!passwordForm.password.trim()" @click="changePassword">更新密码</button>
          </div>
        </SurfaceCard>

        <SurfaceCard v-if="selectedUser" title="用户详情" subtitle="当前选中账号的基础信息。">
          <KeyValueGrid
            :columns="1"
            :items="[
              { label: '用户 ID', value: selectedUser.id },
              { label: '用户名', value: selectedUser.username },
              { label: '昵称', value: selectedUser.nickname || '-' },
              { label: '角色', value: formatRole(selectedUser.role) },
              { label: '状态', value: selectedUser.isActive ? '已启用' : '已停用' },
            ]"
          />
        </SurfaceCard>
      </div>
    </div>

    <SurfaceCard class="mt-5" title="用户审计" subtitle="按时间倒序展示后台账号增删改记录。">
      <div class="inline-actions mb-4">
        <select v-model="auditAction" class="select max-w-xs" @change="loadAudit(1)">
          <option value="">全部动作</option>
          <option value="create">创建</option>
          <option value="update">更新</option>
          <option value="delete">删除</option>
        </select>
        <label class="inline-actions items-center rounded-2xl border border-slate-200 px-4 py-3">
          <input v-model="auditOnlySelected" type="checkbox" :disabled="!selectedUser" @change="loadAudit(1)" />
          <span>仅当前用户</span>
        </label>
        <button class="btn btn-secondary" :disabled="auditLoading" @click="loadAudit(1)">
          {{ auditLoading ? '加载中...' : '刷新' }}
        </button>
      </div>
      <div v-if="auditError" class="helper-text text-red-600">{{ auditError }}</div>
      <div v-else-if="auditRows.length === 0" class="helper-text">暂无用户审计记录。</div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="border-b border-slate-200 text-left text-slate-500">
              <th class="py-2 pr-4 font-medium">时间</th>
              <th class="py-2 pr-4 font-medium">动作</th>
              <th class="py-2 pr-4 font-medium">目标用户</th>
              <th class="py-2 pr-4 font-medium">原值</th>
              <th class="py-2 pr-4 font-medium">新值</th>
              <th class="py-2 pr-4 font-medium">操作者</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in auditRows" :key="row.id" class="border-b border-slate-100">
              <td class="py-3 pr-4 whitespace-nowrap text-slate-600">{{ formatAuditTime(row.createdAt) }}</td>
              <td class="py-3 pr-4 whitespace-nowrap text-slate-700">{{ formatAuditAction(row.action) }}</td>
              <td class="py-3 pr-4 whitespace-nowrap">
                <div class="font-medium text-slate-800">{{ row.targetUsername }}</div>
                <div class="helper-text">{{ row.targetUserId }}</div>
              </td>
              <td class="py-3 pr-4 text-slate-600">{{ formatAuditSnapshot(row.oldValue) }}</td>
              <td class="py-3 pr-4 text-slate-900">{{ formatAuditSnapshot(row.newValue) }}</td>
              <td class="py-3 pr-4 whitespace-nowrap text-slate-600">{{ row.changedBy || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="mt-4 inline-actions justify-between">
        <span class="helper-text">共 {{ auditTotal }} 条，当前第 {{ auditPageNo }} 页</span>
        <div class="inline-actions">
          <button class="btn btn-secondary" :disabled="auditLoading || auditPageNo <= 1" @click="loadAudit(auditPageNo - 1)">上一页</button>
          <button class="btn btn-secondary" :disabled="auditLoading || auditPageNo >= auditTotalPages" @click="loadAudit(auditPageNo + 1)">下一页</button>
        </div>
      </div>
    </SurfaceCard>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

type UserAuditRow = {
  id: string
  action: string
  targetUserId: string
  targetUsername: string
  oldValue: Record<string, any>
  newValue: Record<string, any>
  changedBy: string | null
  createdAt: string | null
}

const loading = ref(false)
const error = ref('')
const users = ref<any[]>([])
const pagination = ref({ total: 0, pageNo: 1, pageSize: 10 })
const selectedUser = ref<any | null>(null)
const form = ref({ id: '', username: '', nickname: '', role: 'user', password: '', isActive: true })
const passwordForm = ref({ password: '' })
const auditRows = ref<UserAuditRow[]>([])
const auditLoading = ref(false)
const auditError = ref('')
const auditAction = ref('')
const auditOnlySelected = ref(false)
const auditPageNo = ref(1)
const auditPageSize = 10
const auditTotal = ref(0)
const auditTotalPages = computed(() => Math.max(1, Math.ceil(auditTotal.value / auditPageSize)))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await adminService.users(pagination.value.pageNo, pagination.value.pageSize)
    users.value = page.items
    pagination.value = { total: page.total, pageNo: page.pageNo, pageSize: page.pageSize }
    if (selectedUser.value) {
      selectedUser.value = users.value.find((item) => item.id === selectedUser.value?.id) || null
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '用户列表加载失败'
  } finally {
    loading.value = false
  }
}

function selectUser(user: any) {
  selectedUser.value = user
  if (auditOnlySelected.value) {
    void loadAudit(1)
  }
}

function edit(user: any) {
  selectedUser.value = user
  form.value = {
    id: user.id,
    username: user.username,
    nickname: user.nickname || '',
    role: user.role,
    password: '',
    isActive: !!user.isActive,
  }
}

function resetForm() {
  form.value = { id: '', username: '', nickname: '', role: 'user', password: '', isActive: true }
}

async function submit() {
  if (form.value.id) {
    await adminService.updateUser(form.value.id, {
      nickname: form.value.nickname,
      role: form.value.role,
      is_active: form.value.isActive,
      ...(form.value.password.trim() ? { password: form.value.password } : {}),
    })
  } else {
    await adminService.createUser({
      username: form.value.username,
      nickname: form.value.nickname,
      password: form.value.password,
      role: form.value.role,
      is_active: form.value.isActive,
    })
  }
  resetForm()
  await load()
  await loadAudit(1)
}

async function remove(id: string) {
  await adminService.deleteUser(id)
  if (selectedUser.value?.id === id) {
    selectedUser.value = null
  }
  if (form.value.id === id) {
    resetForm()
  }
  await load()
  await loadAudit(1)
}

async function changePassword() {
  await adminService.changePassword({ password: passwordForm.value.password })
  passwordForm.value.password = ''
}

function changePage(pageNo: number) {
  pagination.value.pageNo = pageNo
  void load()
}

async function loadAudit(pageNo = auditPageNo.value) {
  auditLoading.value = true
  auditError.value = ''
  try {
    const targetUserId = auditOnlySelected.value ? selectedUser.value?.id || '' : ''
    const page = await adminService.userAuditLogs(pageNo, auditPageSize, targetUserId, auditAction.value)
    auditRows.value = Array.isArray(page.items) ? page.items : []
    auditTotal.value = Number(page.total ?? 0)
    auditPageNo.value = Number(page.pageNo ?? pageNo)
  } catch (err: any) {
    auditError.value = err?.detail || err?.message || '用户审计加载失败'
  } finally {
    auditLoading.value = false
  }
}

function formatRole(role?: string) {
  const map: Record<string, string> = {
    admin: '管理员',
    user: '普通用户',
  }
  return map[String(role || '').toLowerCase()] || role || '-'
}

function formatAuditAction(action?: string) {
  const map: Record<string, string> = {
    create: '创建',
    update: '更新',
    delete: '删除',
  }
  return map[String(action || '').toLowerCase()] || action || '-'
}

function formatAuditSnapshot(value: Record<string, any> | null | undefined) {
  if (!value || Object.keys(value).length === 0) return '-'
  const parts = [
    value.username ? `用户名：${value.username}` : '',
    value.nickname ? `昵称：${value.nickname}` : '',
    value.role ? `角色：${formatRole(value.role)}` : '',
    typeof value.isActive === 'boolean' ? `状态：${value.isActive ? '已启用' : '已停用'}` : '',
    value.passwordChanged ? '密码：已变更' : '',
  ].filter(Boolean)
  return parts.length ? parts.join('；') : '-'
}

function formatAuditTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  load()
  loadAudit()
})
</script>
