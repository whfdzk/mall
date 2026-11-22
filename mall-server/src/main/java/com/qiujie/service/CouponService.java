package com.qiujie.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.entity.Coupon;
import com.qiujie.entity.UserCoupon;

import java.math.BigDecimal;

public interface CouponService {

    IPage<Coupon> page(Page<Coupon> page, String name, Integer type);

    Coupon getById(Integer id);

    void save(Coupon coupon);

    void update(Coupon coupon);

    void delete(Integer id);

    IPage<UserCoupon> pageUserCoupons(Page<UserCoupon> page, Integer userId);

    void claim(Integer couponId, Integer userId);

    BigDecimal calculateDiscount(Integer couponId, Integer userId, BigDecimal orderAmount);

    void lockUserCoupon(Integer couponId, Integer userId, Integer orderId);

    void releaseUserCoupon(Integer orderId);

    void useUserCoupon(Integer orderId);
}