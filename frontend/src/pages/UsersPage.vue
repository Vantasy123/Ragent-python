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
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

const loading = ref(false)
const error = ref('')
const users = ref<any[]>([])
const pagination = ref({ total: 0, pageNo: 1, pageSize: 10 })
const selectedUser = ref<any | null>(null)
const form = ref({ id: '', username: '', nickname: '', role: 'user', password: '', isActive: true })
const passwordForm = ref({ password: '' })

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
}

async function changePassword() {
  await adminService.changePassword({ password: passwordForm.value.password })
  passwordForm.value.password = ''
}

function changePage(pageNo: number) {
  pagination.value.pageNo = pageNo
  void load()
}

function formatRole(role?: string) {
  const map: Record<string, string> = {
    admin: '管理员',
    user: '普通用户',
  }
  return map[String(role || '').toLowerCase()] || role || '-'
}

onMounted(load)
</script>
