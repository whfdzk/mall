package com.qiujie.controller.portal;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.entity.Coupon;
import com.qiujie.entity.UserCoupon;
import com.qiujie.service.CouponService;
import cn.dev33.satoken.stp.StpUtil;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;

@RestController("portalCouponController")
@RequestMapping("/portal/coupon")
public class CouponController {

    @Resource
    private CouponService couponService;

    @GetMapping("/list")
    public ResponseDTO<IPage<Coupon>> listAvailable(
            @RequestParam(defaultValue = "1") Integer current,
            @RequestParam(defaultValue = "10") Integer size) {
        Page<Coupon> page = new Page<>(current, size);
        return Response.success(couponService.page(page, null, null));
    }

    @PostMapping("/claim/{couponId}")
    public ResponseDTO<Void> claim(@PathVariable Integer couponId) {
        couponService.claim(couponId, StpUtil.getLoginIdAsInt());
        return Response.success();
    }

    @GetMapping("/mine")
    public ResponseDTO<IPage<UserCoupon>> mine(
            @RequestParam(defaultValue = "1") Integer current,
            @RequestParam(defaultValue = "10") Integer size) {
        Page<UserCoupon> page = new Page<>(current, size);
        return Response.success(couponService.pageUserCoupons(page, StpUtil.getLoginIdAsInt()));
    }

    @GetMapping("/calculate")
    public ResponseDTO<BigDecimal> calculate(
            @RequestParam Integer couponId,
            @RequestParam BigDecimal orderAmount) {
        BigDecimal discount = couponService.calculateDiscount(
                couponId, StpUtil.getLoginIdAsInt(), orderAmount);
        return Response.success(discount);
    }
}