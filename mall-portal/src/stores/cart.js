import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getCartList, updateCartAmount as apiUpdate, deleteCartItem as apiDelete, batchDeleteCart as apiBatchDelete } from '@/api/cart'
import { useAuthStore } from './auth'

export const useCartStore = defineStore('cart', () => {
  const items = ref([])
  const loaded = ref(false)

  const totalCount = computed(() => items.value.reduce((s, it) => s + (it.amount || 0), 0))
  const totalKinds = computed(() => items.value.length)

  async function refresh() {
    const auth = useAuthStore()
    if (!auth.isLogin) {
      items.value = []
      loaded.value = false
      return
    }
    try {
      const res = await getCartList()
      items.value = res.data || []
      loaded.value = true
    } catch {
      items.value = []
    }
  }

  async function updateAmount(id, amount) {
    await apiUpdate({ id, amount })
    const it = items.value.find(i => i.id === id)
    if (it) it.amount = amount
  }

  async function remove(id) {
    await apiDelete(id)
    items.value = items.value.filter(i => i.id !== id)
  }

  async function batchRemove(ids) {
    await apiBatchDelete(ids)
    items.value = items.value.filter(i => !ids.includes(i.id))
  }

  function reset() {
    items.value = []
    loaded.value = false
  }

  return { items, loaded, totalCount, totalKinds, refresh, updateAmount, remove, batchRemove, reset }
})