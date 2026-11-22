<template>
  <div class="coupon-wrap">
    <div class="breadcrumb">
      <router-link to="/">首页</router-link>
      <span class="sep">/</span>
      <span class="current">我的优惠券</span>
    </div>

    <div class="coupon-layout">
      <UserSidebar active="my-coupons" />

      <div class="main-area">
        <el-tabs v-model="activeTab" class="coupon-tabs">
          <el-tab-pane label="可领券" name="claim">
            <div v-loading="claimLoading" class="coupon-grid">
              <template v-if="claimList.length">
                <div v-for="c in claimList" :key="c.id" class="coupon-card claim-card">
                  <div class="cp-left" :class="'type-' + c.type">
                    <div class="cp-value">
                      <span v-if="c.type === 1 || c.type === 3" class="cp-symbol">¥</span>
                      <span class="cp-num">{{ c.type === 2 ? c.discountValue : c.discountValue }}</span>
                      <span v-if="c.type === 2" class="cp-unit">折</span>
                    </div>
                    <div class="cp-condition">{{ c.type === 1 ? `满¥${c.thresholdAmount}可用` : c.type === 2 ? '折扣券' : '无门槛' }}</div>
                  </div>
                  <div class="cp-right">
                    <div class="cp-name">{{ c.name }}</div>
                    <div class="cp-time">{{ c.startTime?.slice(0, 10) }} ~ {{ c.endTime?.slice(0, 10) }}</div>
                    <div class="cp-meta">
                      剩余 {{ c.totalStock }} | 每人限领 {{ c.perLimit }}
                    </div>
                    <el-button type="danger" size="small" class="cp-btn" @click="handleClaim(c.id)" :loading="claimingId === c.id">
                      立即领取
                    </el-button>
                  </div>
                </div>
              </template>
              <el-empty v-else description="暂无可领取的优惠券" />
            </div>
          </el-tab-pane>

          <el-tab-pane label="我的券" name="mine">
            <div class="mine-filter">
              <span v-for="f in filters" :key="f.value" :class="['filter-tag', { active: mineFilter === f.value }]" @click="mineFilter = f.value">
                {{ f.label }} ({{ f.count }})
              </span>
            </div>
            <div v-loading="mineLoading" class="coupon-grid">
              <template v-if="filteredMineList.length">
                <div v-for="uc in filteredMineList" :key="uc.id" class="coupon-card mine-card" :class="'status-' + uc.status">
                  <div class="cp-left" :class="'type-' + uc.couponType">
                    <div class="cp-value">
                      <span v-if="uc.couponType === 1 || uc.couponType === 3" class="cp-symbol">¥</span>
                      <span class="cp-num">{{ uc.couponType === 2 ? uc.discountValue : uc.discountValue }}</span>
                      <span v-if="uc.couponType === 2" class="cp-unit">折</span>
                    </div>
                    <div class="cp-condition">{{ uc.couponType === 1 ? `满¥${uc.thresholdAmount}可用` : uc.couponType === 2 ? '折扣券' : '无门槛' }}</div>
                  </div>
                  <div class="cp-right">
                    <div class="cp-name">{{ uc.couponName }}</div>
                    <div class="cp-time">有效期至 {{ uc.endTime?.slice(0, 10) }}</div>
                    <div class="cp-status">
                      <el-tag v-if="uc.status === 0" type="success" size="small">未使用</el-tag>
                      <el-tag v-else-if="uc.status === 1" type="warning" size="small">已锁定</el-tag>
                      <el-tag v-else-if="uc.status === 2" type="info" size="small">已使用</el-tag>
                      <el-tag v-else type="info" size="small">已过期</el-tag>
                    </div>
                    <router-link v-if="uc.status === 0" to="/cart" class="cp-use-btn">去使用 →</router-link>
                  </div>
                </div>
              </template>
              <el-empty v-else description="暂无优惠券" />
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import UserSidebar from '../components/UserSidebar.vue'
import { getClaimList, claimCoupon, getMyCoupons } from '@/api'

const activeTab = ref('claim')
const claimLoading = ref(false)
const mineLoading = ref(false)
const claimList = ref([])
const mineList = ref([])
const mineFilter = ref('all')
const claimingId = ref(null)

const filters = computed(() => {
  const list = mineList.value
  return [
    { label: '全部', value: 'all', count: list.length },
    { label: '未使用', value: '0', count: list.filter(x => x.status === 0).length },
    { label: '已锁定', value: '1', count: list.filter(x => x.status === 1).length },
    { label: '已使用', value: '2', count: list.filter(x => x.status === 2).length },
    { label: '已过期', value: '3', count: list.filter(x => x.status === 3).length }
  ]
})

const filteredMineList = computed(() => {
  if (mineFilter.value === 'all') return mineList.value
  return mineList.value.filter(x => String(x.status) === mineFilter.value)
})

const fetchClaimList = async () => {
  claimLoading.value = true
  try {
    const res = await getClaimList()
    claimList.value = res.data || []
  } catch {} finally { claimLoading.value = false }
}

const fetchMine = async () => {
  mineLoading.value = true
  try {
    const res = await getMyCoupons({ current: 1, size: 100 })
    mineList.value = res.data?.records || []
  } catch {} finally { mineLoading.value = false }
}

const handleClaim = async (couponId) => {
  claimingId.value = couponId
  try {
    await claimCoupon(couponId)
    ElMessage.success('领取成功')
    fetchClaimList()
    if (activeTab.value === 'mine') fetchMine()
  } catch (e) {
    ElMessage.error(e?.message || '领取失败')
  } finally { claimingId.value = null }
}

onMounted(() => { fetchClaimList(); fetchMine() })
</script>

<style scoped>
.coupon-wrap { width: 1160px; margin: 0 auto; padding: 24px 0; }

.breadcrumb { font-size: 13px; color: #999; margin-bottom: 24px; }
.breadcrumb a { color: #666; text-decoration: none; }
.breadcrumb a:hover { color: #A10000; }
.sep { margin: 0 8px; color: #ccc; }
.current { color: #333; }

.coupon-layout { display: flex; gap: 24px; }
.main-area { flex: 1; min-width: 0; }

.coupon-tabs :deep(.el-tabs__item.is-active) { color: #A10000; }
.coupon-tabs :deep(.el-tabs__active-bar) { background-color: #A10000; }

.mine-filter { display: flex; gap: 12px; margin-bottom: 16px; }
.filter-tag { padding: 6px 16px; border: 1px solid #e0e0e0; border-radius: 20px;
  font-size: 13px; color: #666; cursor: pointer; transition: all .15s; }
.filter-tag:hover { border-color: #A10000; color: #A10000; }
.filter-tag.active { border-color: #A10000; background: #A10000; color: #fff; }

.coupon-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.coupon-card { display: flex; background: #fff; border-radius: 12px; overflow: hidden;
  border: 1px solid #eee; transition: all .2s; }
.coupon-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); transform: translateY(-2px); }

.cp-left { width: 140px; flex-shrink: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; color: #fff; padding: 16px 0; position: relative; }
.cp-left.type-1 { background: linear-gradient(135deg, #ff6b6b, #ee5a24); }
.cp-left.type-2 { background: linear-gradient(135deg, #26de81, #20bf6b); }
.cp-left.type-3 { background: linear-gradient(135deg, #fed330, #f7b731); }

.coupon-card.mine-card.status-2 .cp-left,
.coupon-card.mine-card.status-3 .cp-left { background: linear-gradient(135deg, #b2bec3, #95a5a6); }

.cp-value { display: flex; align-items: baseline; }
.cp-symbol { font-size: 16px; font-weight: 500; }
.cp-num { font-size: 36px; font-weight: 700; line-height: 1; }
.cp-unit { font-size: 14px; margin-left: 2px; }
.cp-condition { font-size: 12px; margin-top: 6px; opacity: 0.9; }

.cp-right { flex: 1; padding: 14px 18px; display: flex; flex-direction: column; justify-content: space-between; }
.cp-name { font-size: 15px; font-weight: 600; color: #222; }
.cp-time { font-size: 12px; color: #999; margin-top: 4px; }
.cp-meta { font-size: 12px; color: #bbb; margin-top: 4px; }
.cp-status { margin-top: 6px; }

.cp-btn { margin-top: 8px; width: 100%; }
.cp-use-btn { margin-top: 8px; color: #A10000; font-size: 13px; text-decoration: none; font-weight: 500; }
.cp-use-btn:hover { text-decoration: underline; }

.coupon-card.mine-card.status-2,
.coupon-card.mine-card.status-3 { opacity: 0.7; }
</style>