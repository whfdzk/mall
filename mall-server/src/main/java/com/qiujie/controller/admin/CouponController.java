package com.qiujie.controller.admin;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.entity.Coupon;
import com.qiujie.service.CouponService;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController("adminCouponController")
@RequestMapping("/admin/coupon")
public class CouponController {

    @Resource
    private CouponService couponService;

    @GetMapping("/page")
    public ResponseDTO<IPage<Coupon>> page(
            @RequestParam(defaultValue = "1") Integer current,
            @RequestParam(defaultValue = "10") Integer size,
            @RequestParam(required = false) String name,
            @RequestParam(required = false) Integer type) {
        Page<Coupon> page = new Page<>(current, size);
        return Response.success(couponService.page(page, name, type));
    }

    @GetMapping("/{id}")
    public ResponseDTO<Coupon> getById(@PathVariable Integer id) {
        return Response.success(couponService.getById(id));
    }

    @PostMapping
    public ResponseDTO<Void> save(@Valid @RequestBody Coupon coupon) {
        couponService.save(coupon);
        return Response.success();
    }

    @PutMapping
    public ResponseDTO<Void> update(@Valid @RequestBody Coupon coupon) {
        couponService.update(coupon);
        return Response.success();
    }

    @DeleteMapping("/{id}")
    public ResponseDTO<Void> delete(@PathVariable Integer id) {
        couponService.delete(id);
        return Response.success();
    }
}