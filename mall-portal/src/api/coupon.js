import request from '@/utils/request'
const url = '/coupon'

export const getClaimList = () => request.get(`${url}/list`)
export const claimCoupon = (couponId) => request.post(`${url}/claim/${couponId}`)
export const getMyCoupons = (params) => request.get(`${url}/mine`, { params })
export const calculateDiscount = (couponId, orderAmount) => request.get(`${url}/calculate`, { params: { couponId, orderAmount } })