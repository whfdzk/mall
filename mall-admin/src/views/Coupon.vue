<template>
  <div class="page-container">
    <el-card class="page-table" shadow="never">
      <div class="page-table-actions">
        <el-input v-model="query.name" placeholder="券名称" style="width:180px;margin-right:10px" clearable />
        <el-select v-model="query.type" placeholder="券类型" style="width:140px;margin-right:10px" clearable>
          <el-option label="满减券" :value="1" />
          <el-option label="折扣券" :value="2" />
          <el-option label="无门槛券" :value="3" />
        </el-select>
        <el-button type="primary" :icon="'Search'" @click="fetchData">搜索</el-button>
        <el-button type="success" :icon="'Plus'" @click="handleAdd" style="margin-left:auto">新建优惠券</el-button>
      </div>
      <el-table :data="tableData" border v-loading="loading">
        <template #empty><el-empty description="暂无优惠券" /></template>
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="name" label="券名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="100" align="center">
          <template #default="{row}">
            <el-tag :type="typeTag(row.type).type" size="small">{{ typeTag(row.type).text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="优惠规则" min-width="160" align="center">
          <template #default="{row}">{{ ruleText(row) }}</template>
        </el-table-column>
        <el-table-column prop="totalStock" label="总量" width="80" align="center" />
        <el-table-column prop="perLimit" label="每人限领" width="100" align="center" />
        <el-table-column label="有效期" min-width="260" align="center">
          <template #default="{row}">{{ row.startTime }} ~ {{ row.endTime }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{row}">
            <el-tag :type="statusTag(row).type" size="small">{{ statusTag(row).text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{row}">
            <el-button type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="page-table-pagination">
        <el-pagination v-model:current-page="query.current" v-model:page-size="query.size" :total="total"
          layout="total, sizes, prev, pager, next" :page-sizes="[10, 20, 50]" @current-change="fetchData" @size-change="fetchData" />
      </div>
    </el-card>

    <el-dialog :title="isEdit ? '编辑优惠券' : '新建优惠券'" v-model="dialogVisible" width="520px" destroy-on-close>
      <el-form :model="form" label-width="100px" :rules="formRules" ref="formRef">
        <el-form-item label="券名称" prop="name">
          <el-input v-model="form.name" placeholder="如：双11满200减30" />
        </el-form-item>
        <el-form-item label="券类型" prop="type">
          <el-radio-group v-model="form.type">
            <el-radio :value="1">满减券</el-radio>
            <el-radio :value="2">折扣券</el-radio>
            <el-radio :value="3">无门槛券</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.type === 1" label="门槛金额" prop="thresholdAmount">
          <el-input-number v-model="form.thresholdAmount" :min="0.01" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item v-if="form.type === 1 || form.type === 3" label="优惠金额" prop="discountValue">
          <el-input-number v-model="form.discountValue" :min="0.01" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item v-if="form.type === 2" label="折扣值" prop="discountValue">
          <el-input-number v-model="form.discountValue" :min="1" :max="9.9" :step="0.1" :precision="1" />
          <div class="form-tip">如 8 表示 8 折，6.5 表示 65 折</div>
        </el-form-item>
        <el-form-item label="发行总量" prop="totalStock">
          <el-input-number v-model="form.totalStock" :min="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="每人限领" prop="perLimit">
          <el-input-number v-model="form.perLimit" :min="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="开始时间" prop="startTime">
          <el-date-picker v-model="form.startTime" type="datetime" placeholder="选择开始时间"
            value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束时间" prop="endTime">
          <el-date-picker v-model="form.endTime" type="datetime" placeholder="选择结束时间"
            value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">{{ isEdit ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { page, create, update, remove } from '@/api/coupon'
import { ElMessage, ElMessageBox } from 'element-plus'

const tableData = ref([])
const total = ref(0)
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const query = reactive({ current: 1, size: 10, name: '', type: null })
const form = reactive({
  id: null, name: '', type: 1, thresholdAmount: null,
  discountValue: null, totalStock: 100, perLimit: 1, startTime: '', endTime: ''
})

const formRules = {
  name: [{ required: true, message: '请输入券名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择券类型', trigger: 'change' }],
  totalStock: [{ required: true, message: '请输入发行总量', trigger: 'blur' }],
  perLimit: [{ required: true, message: '请输入每人限领', trigger: 'blur' }],
  startTime: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
  endTime: [{ required: true, message: '请选择结束时间', trigger: 'change' }]
}

const typeTag = (t) => ({ 1: { text: '满减券', type: 'warning' }, 2: { text: '折扣券', type: 'success' }, 3: { text: '无门槛券', type: 'danger' } }[t] || { text: '未知', type: 'info' })

const statusTag = (row) => {
  const now = new Date()
  const start = new Date(row.startTime)
  const end = new Date(row.endTime)
  if (now < start) return { text: '未开始', type: 'warning' }
  if (now > end) return { text: '已过期', type: 'info' }
  return { text: '进行中', type: 'success' }
}

const ruleText = (row) => {
  if (row.type === 1) return `满 ¥${row.thresholdAmount} 减 ¥${row.discountValue}`
  if (row.type === 2) return `${row.discountValue} 折`
  return `立减 ¥${row.discountValue}`
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await page(query)
    tableData.value = res.data.records || []
    total.value = res.data.total || 0
  } finally { loading.value = false }
}

const handleAdd = () => {
  isEdit.value = false
  Object.assign(form, {
    id: null, name: '', type: 1, thresholdAmount: null,
    discountValue: null, totalStock: 100, perLimit: 1, startTime: '', endTime: ''
  })
  dialogVisible.value = true
}

const handleEdit = (row) => {
  isEdit.value = true
  Object.assign(form, row)
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  if (form.type === 1 && form.thresholdAmount == null) {
    ElMessage.warning('满减券请填写门槛金额'); return
  }
  if (form.discountValue == null) {
    ElMessage.warning('请填写优惠值'); return
  }
  try {
    if (isEdit.value) {
      await update(form)
      ElMessage.success('更新成功')
    } else {
      await create(form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } catch (e) { ElMessage.error(e?.message || '操作失败') }
}

const handleDelete = async (id) => {
  await ElMessageBox.confirm('确定删除该优惠券？', '提示', { type: 'warning' })
  try {
    await remove(id)
    ElMessage.success('删除成功')
    fetchData()
  } catch {}
}

onMounted(() => fetchData())
</script>

<style scoped>
.page-container { padding: 16px; }
.page-table { margin-bottom: 16px; }
.page-table-actions { margin-bottom: 16px; display: flex; align-items: center; }
.page-table-pagination { display: flex; justify-content: flex-end; margin-top: 16px; }
.form-tip { font-size: 12px; color: #999; margin-top: 4px; }
</style>