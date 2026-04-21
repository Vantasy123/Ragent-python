<template>
  <section>
    <PageHeader
      title="用户管理"
      eyebrow="Access Control"
      description="管理后台账号、角色和启停状态，同时支持当前登录账号修改密码。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新</button>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="用户表单" subtitle="创建新用户或编辑已有账号的昵称、角色和状态。">
        <div class="form-grid form-grid-two">
          <input v-model="form.username" class="input" :disabled="!!form.id" placeholder="用户名" />
          <input v-model="form.nickname" class="input" placeholder="显示名称" />
          <select v-model="form.role" class="select">
            <option value="admin">admin</option>
            <option value="user">user</option>
          </select>
          <input
            v-model="form.password"
            type="password"
            class="input"
            :disabled="!!form.id"
            :placeholder="form.id ? '编辑已有用户时不在这里修改密码' : '初始密码'"
          />
        </div>
        <label class="mt-4 inline-actions items-center">
          <input v-model="form.isActive" type="checkbox" />
          <span>启用用户</span>
        </label>
        <div class="mt-4 inline-actions">
          <button class="btn btn-primary" :disabled="!form.username.trim() || (!form.id && !form.password.trim())" @click="submit">
            {{ form.id ? '保存用户' : '创建用户' }}
          </button>
          <button v-if="form.id" class="btn btn-secondary" @click="resetForm">取消编辑</button>
        </div>
      </SurfaceCard>

      <SurfaceCard title="修改当前账号密码" subtitle="该接口只作用于当前登录用户，不支持替他人改密。">
        <div class="form-grid">
          <input v-model="passwordForm.password" type="password" class="input" placeholder="输入新密码" />
          <button class="btn btn-primary" :disabled="!passwordForm.password.trim()" @click="changePassword">更新密码</button>
        </div>
      </SurfaceCard>
    </div>

    <SurfaceCard class="mt-5" title="用户列表" subtitle="查看全部账号，并对单个账号执行编辑或删除。">
      <AsyncState
        :loading="loading"
        :error="error"
        :empty="!users.length"
        empty-title="暂无用户"
        empty-description="至少保留一个管理员账号以保证后台可管理。"
      >
        <div class="list-stack">
          <article v-for="user in users" :key="user.id" class="resource-item">
            <div class="resource-item-row">
              <div class="mini-stack">
                <div class="resource-title">{{ user.nickname || user.username }}</div>
                <div class="resource-meta">
                  <span>{{ user.username }}</span>
                  <span>{{ user.role }}</span>
                </div>
              </div>
              <span :class="statusClass(user.isActive ? 'enabled' : 'disabled')" class="status-badge">
                {{ user.isActive ? 'enabled' : 'disabled' }}
              </span>
            </div>
            <div class="mt-3">
              <KeyValueGrid
                :columns="1"
                :items="[
                  { label: '用户 ID', value: user.id },
                  { label: '角色', value: user.role },
                ]"
              />
            </div>
            <div class="mt-3 inline-actions">
              <button class="btn btn-secondary" @click="edit(user)">编辑</button>
              <button class="btn btn-danger" @click="remove(user.id)">删除</button>
            </div>
          </article>
        </div>
      </AsyncState>
    </SurfaceCard>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

const loading = ref(false)
const error = ref('')
const users = ref<any[]>([])
const form = ref({ id: '', username: '', nickname: '', role: 'user', password: '', isActive: true })
const passwordForm = ref({ password: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await adminService.users()
    users.value = page.items
  } catch (err: any) {
    error.value = err?.detail || err?.message || '用户列表加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (form.value.id) {
    await adminService.updateUser(form.value.id, {
      nickname: form.value.nickname,
      role: form.value.role,
      is_active: form.value.isActive,
    })
  } else {
    await adminService.createUser({
      username: form.value.username,
      nickname: form.value.nickname,
      password: form.value.password,
      role: form.value.role,
    })
  }
  resetForm()
  await load()
}

function edit(user: any) {
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

async function remove(id: string) {
  await adminService.deleteUser(id)
  if (form.value.id === id) resetForm()
  await load()
}

async function changePassword() {
  await adminService.changePassword({ password: passwordForm.value.password })
  passwordForm.value.password = ''
}

function statusClass(status: string) {
  return status === 'enabled' ? 'status-badge-success' : 'status-badge-danger'
}

onMounted(load)
</script>
