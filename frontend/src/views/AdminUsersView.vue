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
    class="admin-page"
    v-motion
    :initial="{ opacity: 0, y: 18 }"
    :enter="{ opacity: 1, y: 0 }"
  >
    <header class="control-header">
      <div>
        <p class="panel-kicker">{{ t('adminUsers.kicker') }}</p>
        <h1>{{ t('adminUsers.title') }}</h1>
        <p class="section-note">{{ t('adminUsers.note') }}</p>
      </div>
      <div class="status-chips">
        <div class="status-chip">
          <span>{{ t('adminUsers.totalUsers') }}</span>
          <strong>{{ totalUsers }}</strong>
        </div>
        <div class="status-chip danger">
          <span>{{ t('adminUsers.totalAdmins') }}</span>
          <strong>{{ totalAdmins }}</strong>
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
        <div class="card-head">
          <h2>{{ t('adminUsers.userListTitle') }}</h2>
          <el-button :loading="loadingUsers" @click="loadUsers">{{
            t('adminUsers.refresh')
          }}</el-button>
        </div>
        <el-table :data="users" v-loading="loadingUsers" class="users-table" height="420">
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
      </el-card>

      <el-card class="admin-card create-card" shadow="never">
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
          <el-button class="submit-btn" type="primary" native-type="submit" :loading="creatingUser">
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

.control-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
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

.status-chip {
  min-width: 132px;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  background: linear-gradient(150deg, rgba(25, 40, 63, 0.95), rgba(11, 20, 35, 0.96));
  display: grid;
  gap: 0.2rem;
}

.status-chip span {
  font-size: 0.72rem;
  color: var(--terminal-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'IBM Plex Mono', monospace;
}

.status-chip strong {
  font-size: 1.25rem;
}

.status-chip.danger {
  box-shadow: inset 0 0 0 1px rgba(247, 83, 113, 0.25);
}

.admin-grid {
  display: grid;
  grid-template-columns: 1.45fr 0.95fr;
  gap: 1rem;
}

.admin-card {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(9, 16, 30, 0.97));
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
  margin-bottom: 0.6rem;
}

h2 {
  margin: 0;
}

.users-table {
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  overflow: hidden;
}

.submit-btn {
  width: 100%;
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
