<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { adminApi, type AdminUser } from '../api/admin'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const { t } = useI18n()

const loadingUsers = ref(false)
const creatingUser = ref(false)
const errorMessage = ref('')
const users = ref<AdminUser[]>([])

const createForm = reactive({
  username: '',
  email: '',
  password: '',
  user_level: 'user' as 'user' | 'admin',
})

const totalUsers = computed(() => users.value.length)
const totalAdmins = computed(
  () => users.value.filter((item) => item.user_level === 'admin').length,
)
const activeUsers = computed(
  () => users.value.filter((item) => item.is_active).length,
)

const accessToken = computed(() => authStore.accessToken)

const userLevelLabel = (level: 'user' | 'admin') => {
  return level === 'admin' ? t('adminUsers.levelAdmin') : t('adminUsers.levelUser')
}

const formatDateTime = (value: string | null) => {
  if (!value) {
    return '--'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

const loadUsers = async () => {
  errorMessage.value = ''
  loadingUsers.value = true

  try {
    // 鉴权边界：后台接口必须携带 access token，缺失时立刻终止请求，避免无意义重试。
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    // 后台用户列表只读加载，避免在此处做额外过滤以免与服务端口径不一致。
    users.value = await adminApi.listUsers(accessToken.value)
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loadingUsers.value = false
  }
}

const submitCreateUser = async () => {
  errorMessage.value = ''
  creatingUser.value = true

  try {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    // 关键流程：提交前做输入清洗，避免多余空格导致“重复账号/邮箱”误判。
    await adminApi.createUser(accessToken.value, {
      username: createForm.username.trim(),
      email: createForm.email.trim(),
      password: createForm.password,
      user_level: createForm.user_level,
    })

    // 关键状态流转：创建成功后先清空表单，再刷新列表，避免重复提交和脏数据残留。
    createForm.username = ''
    createForm.email = ''
    createForm.password = ''
    createForm.user_level = 'user'
    await loadUsers()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    creatingUser.value = false
  }
}

onMounted(async () => {
  await loadUsers()
})
</script>

<template>
  <section
    data-testid="admin-users-neo-shell"
    class="admin-page"
    v-motion
    :initial="{ opacity: 0, y: 18 }"
    :enter="{ opacity: 1, y: 0 }"
  >
    <header class="control-header neo-hero">
      <div class="hero-copy">
        <p class="panel-kicker">{{ t('adminUsers.kicker') }}</p>
        <h1>{{ t('adminUsers.title') }}</h1>
        <p class="section-note">{{ t('adminUsers.note') }}</p>
      </div>
      <div class="status-chips hero-chips">
        <div class="status-chip">
          <span>USERS</span>
          <strong>{{ totalUsers }}</strong>
          <em>{{ t('adminUsers.totalUsers') }}</em>
        </div>
        <div class="status-chip danger">
          <span>ADMINS</span>
          <strong>{{ totalAdmins }}</strong>
          <em>{{ t('adminUsers.totalAdmins') }}</em>
        </div>
        <div class="status-chip success">
          <span>ACTIVE</span>
          <strong>{{ activeUsers }}</strong>
          <em>{{ t('profile.active') }}</em>
        </div>
      </div>
    </header>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="admin-grid">
      <el-card class="admin-card data-card" shadow="never">
        <div class="card-head list-head">
          <div>
            <p class="mini-kicker">USER DIRECTORY</p>
            <h2>{{ t('adminUsers.userListTitle') }}</h2>
          </div>
          <el-button data-testid="admin-users-refresh" :loading="loadingUsers" @click="loadUsers">{{
            t('adminUsers.refresh')
          }}</el-button>
        </div>

        <div class="table-shell">
          <el-table
            data-testid="admin-users-table"
            :data="users"
            v-loading="loadingUsers"
            class="users-table theme-table"
            height="430"
          >
            <el-table-column prop="username" :label="t('adminUsers.username')" min-width="130" />
            <el-table-column prop="email" :label="t('adminUsers.email')" min-width="190" />
            <el-table-column :label="t('adminUsers.level')" min-width="120">
              <template #default="scope">
                <el-tag :type="scope.row.user_level === 'admin' ? 'danger' : 'info'">
                  {{ userLevelLabel(scope.row.user_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('adminUsers.lastLogin')" min-width="190">
              <template #default="scope">
                {{ formatDateTime(scope.row.last_login_at) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>

      <el-card class="admin-card create-card" shadow="never">
        <p class="mini-kicker">ACCESS PROVISION</p>
        <h2>{{ t('adminUsers.createTitle') }}</h2>
        <p class="section-note">{{ t('adminUsers.createNote') }}</p>

        <el-form label-position="top" @submit.prevent="submitCreateUser">
          <el-form-item :label="t('adminUsers.username')">
            <el-input v-model="createForm.username" :placeholder="t('adminUsers.usernamePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('adminUsers.email')">
            <el-input v-model="createForm.email" :placeholder="t('adminUsers.emailPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('adminUsers.password')">
            <el-input
              v-model="createForm.password"
              type="password"
              show-password
              :placeholder="t('adminUsers.passwordPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('adminUsers.level')">
            <el-segmented
              v-model="createForm.user_level"
              :options="[
                { label: t('adminUsers.levelUser'), value: 'user' },
                { label: t('adminUsers.levelAdmin'), value: 'admin' },
              ]"
            />
          </el-form-item>
          <el-button
            data-testid="admin-users-create"
            class="submit-btn"
            type="primary"
            native-type="submit"
            :loading="creatingUser"
          >
            {{ t('adminUsers.createButton') }}
          </el-button>
        </el-form>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.admin-page {
  display: grid;
  gap: 1rem;
}

.neo-hero {
  position: relative;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--terminal-border) 85%, transparent);
  border-radius: 18px;
  padding: 1rem 1.05rem;
  background: var(--terminal-hero-bg);
  box-shadow: var(--terminal-shadow);
}

.neo-hero::after {
  content: '';
  position: absolute;
  inset: auto -26% -56% auto;
  width: 280px;
  height: 280px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(247, 181, 0, 0.16), transparent 72%);
  pointer-events: none;
}

.control-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.hero-copy {
  position: relative;
  z-index: 1;
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: #f7b500;
  letter-spacing: 0.14em;
  font-size: 0.74rem;
  text-transform: uppercase;
}

h1 {
  margin: 0.38rem 0 0.25rem;
}

.section-note {
  margin: 0;
  color: var(--terminal-muted);
}

.status-chips {
  display: flex;
  gap: 0.6rem;
}

.hero-chips {
  position: relative;
  z-index: 1;
}

.status-chip {
  min-width: 132px;
  padding: 0.58rem 0.8rem;
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  background: var(--terminal-card-elevated-bg);
  display: grid;
  gap: 0.18rem;
}

.status-chip span {
  font-size: 0.68rem;
  color: var(--terminal-muted);
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-family: 'IBM Plex Mono', monospace;
}

.status-chip strong {
  font-size: 1.2rem;
}

.status-chip em {
  font-style: normal;
  font-size: 0.68rem;
  color: color-mix(in srgb, var(--terminal-muted) 84%, var(--terminal-text) 16%);
}

.status-chip.danger {
  box-shadow: inset 0 0 0 1px rgba(247, 83, 113, 0.25);
}

.status-chip.success {
  box-shadow: inset 0 0 0 1px rgba(24, 178, 106, 0.25);
}

.admin-grid {
  display: grid;
  grid-template-columns: 1.45fr 0.95fr;
  gap: 1rem;
}

.admin-card {
  border: 1px solid var(--terminal-border);
  border-radius: 18px;
  background: var(--terminal-card-strong-bg);
  box-shadow: var(--terminal-shadow);
  position: relative;
  overflow: hidden;
}

.admin-card::after {
  content: '';
  position: absolute;
  inset: auto -35% -35% auto;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(247, 181, 0, 0.18), transparent 72%);
  pointer-events: none;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.72rem;
}

.list-head {
  padding-bottom: 0.55rem;
  border-bottom: 1px dashed color-mix(in srgb, var(--terminal-border) 72%, transparent);
}

.mini-kicker {
  margin: 0;
  color: color-mix(in srgb, var(--terminal-primary) 84%, white 16%);
  font-family: 'IBM Plex Mono', monospace;
  letter-spacing: 0.14em;
  font-size: 0.66rem;
  text-transform: uppercase;
}

h2 {
  margin: 0.24rem 0 0;
}

.users-table {
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  overflow: hidden;
}

.table-shell {
  border: 1px solid color-mix(in srgb, var(--terminal-border) 75%, transparent);
  border-radius: 14px;
  padding: 0.45rem;
  background: var(--terminal-card-table-shell-bg);
}

.create-card .section-note {
  margin-bottom: 0.75rem;
}

.submit-btn {
  width: 100%;
  margin-top: 0.2rem;
}

@media (max-width: 980px) {
  .admin-grid {
    grid-template-columns: 1fr;
  }

  .control-header {
    flex-direction: column;
  }
}
</style>
