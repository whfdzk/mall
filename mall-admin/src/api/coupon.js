import request from '@/utils/request'
const url = '/coupon'

export const page = (params) => request.get(`${url}/page`, { params })
export const detail = (id) => request.get(`${url}/${id}`)
export const create = (data) => request.post(url, data)
export const update = (data) => request.put(url, data)
export const remove = (id) => request.delete(`${url}/${id}`)