package com.qiujie.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.constants.RedisConstants;
import com.qiujie.entity.Coupon;
import com.qiujie.entity.UserCoupon;
import com.qiujie.enums.BusinessStatusEnum;
import com.qiujie.enums.UserCouponStatusEnum;
import com.qiujie.exception.ServiceException;
import com.qiujie.mapper.CouponMapper;
import com.qiujie.mapper.UserCouponMapper;
import com.qiujie.service.CouponService;
import com.qiujie.util.RedisUtil;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.List;

@Slf4j
@Service
public class CouponServiceImpl implements CouponService {

    @Resource
    private CouponMapper couponMapper;
    @Resource
    private UserCouponMapper userCouponMapper;
    @Resource
    private RedisUtil redisUtil;

    // ==================== 管理端 CRUD ====================

    @Override
    public IPage<Coupon> page(Page<Coupon> page, String name, Integer type) {
        QueryWrapper<Coupon> wrapper = new QueryWrapper<>();
        if (name != null && !name.isBlank()) {
            wrapper.like("name", name);
        }
        if (type != null) {
            wrapper.eq("type", type);
        }
        wrapper.orderByDesc("create_time");
        return couponMapper.selectPage(page, wrapper);
    }

    @Override
    public Coupon getById(Integer id) {
        Coupon coupon = couponMapper.selectById(id);
        if (coupon == null) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_EXIST);
        }
        return coupon;
    }

    @Override
    @Transactional
    public void save(Coupon coupon) {
        coupon.setCreateTime(LocalDateTime.now());
        coupon.setUpdateTime(LocalDateTime.now());
        couponMapper.insert(coupon);
    }

    @Override
    @Transactional
    public void update(Coupon coupon) {
        Coupon exist = couponMapper.selectById(coupon.getId());
        if (exist == null) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_EXIST);
        }
        coupon.setUpdateTime(LocalDateTime.now());
        couponMapper.updateById(coupon);
    }

    @Override
    @Transactional
    public void delete(Integer id) {
        Coupon coupon = couponMapper.selectById(id);
        if (coupon == null) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_EXIST);
        }
        couponMapper.deleteById(id);
    }

    // ==================== 用户端 ====================

    @Override
    public IPage<UserCoupon> pageUserCoupons(Page<UserCoupon> page, Integer userId) {
        return userCouponMapper.selectUserCouponsWithDetail(page, userId);
    }

    @Override
    @Transactional
    public void claim(Integer couponId, Integer userId) {
        Coupon coupon = couponMapper.selectById(couponId);
        if (coupon == null) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_EXIST);
        }

        LocalDateTime now = LocalDateTime.now();
        if (now.isBefore(coupon.getStartTime()) || now.isAfter(coupon.getEndTime())) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_ACTIVE);
        }

        String stockKey = "coupon:stock:" + couponId;
        String userKey = "coupon:claimed:" + couponId;

        String lua = """
                local stockKey = KEYS[1]
                local userKey = KEYS[2]
                local initStock = tonumber(ARGV[1])
                local perLimit = tonumber(ARGV[2])
                local userId = ARGV[3]

                if redis.call('EXISTS', stockKey) == 0 then
                    redis.call('SET', stockKey, initStock)
                end

                local claimed = redis.call('SCARD', userKey)
                if claimed >= perLimit then
                    return -1
                end

                local raw = redis.call('GET', stockKey) or '0'
                raw = raw:gsub('"', '')
                local stock = tonumber(raw)
                if stock <= 0 then
                    return -2
                end

                redis.call('SET', stockKey, stock - 1)
                redis.call('SADD', userKey, userId)
                return 1
                """;

        Long result = redisUtil.executeLua(lua, Long.class,
                List.of(stockKey, userKey),
                coupon.getTotalStock(), coupon.getPerLimit(), userId.toString());

        if (result == null) {
            throw new ServiceException(BusinessStatusEnum.ERROR);
        }
        if (result == -1) {
            throw new ServiceException(BusinessStatusEnum.COUPON_LIMIT_EXCEEDED);
        }
        if (result == -2) {
            throw new ServiceException(BusinessStatusEnum.COUPON_STOCK_EMPTY);
        }

        try {
            UserCoupon userCoupon = new UserCoupon();
            userCoupon.setUserId(userId);
            userCoupon.setCouponId(couponId);
            userCoupon.setStatus(UserCouponStatusEnum.UNUSED);
            userCoupon.setCreateTime(LocalDateTime.now());
            userCoupon.setUpdateTime(LocalDateTime.now());
            userCouponMapper.insert(userCoupon);
        } catch (Exception e) {
            String rollbackLua = """
                    local raw = redis.call('GET', KEYS[1])
                    if raw then
                        raw = raw:gsub('"', '')
                        redis.call('SET', KEYS[1], tonumber(raw) + 1)
                    end
                    redis.call('SREM', KEYS[2], ARGV[1])
                    """;
            redisUtil.executeLua(rollbackLua, Void.class,
                    List.of(stockKey, userKey), userId.toString());
            throw new ServiceException(BusinessStatusEnum.COUPON_CLAIM_FAILED);
        }
    }

    @Override
    public BigDecimal calculateDiscount(Integer couponId, Integer userId, BigDecimal orderAmount) {
        UserCoupon userCoupon = userCouponMapper.selectOne(new QueryWrapper<UserCoupon>()
                .eq("coupon_id", couponId)
                .eq("user_id", userId)
                .eq("status", UserCouponStatusEnum.UNUSED));
        if (userCoupon == null) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_AVAILABLE);
        }

        Coupon coupon = couponMapper.selectById(couponId);
        if (coupon == null) {
            throw new ServiceException(BusinessStatusEnum.COUPON_NOT_EXIST);
        }

        LocalDateTime now = LocalDateTime.now();
        if (now.isBefore(coupon.getStartTime()) || now.isAfter(coupon.getEndTime())) {
            throw new ServiceException(BusinessStatusEnum.COUPON_EXPIRED);
        }

        switch (coupon.getType()) {
            case FULL_REDUCTION:
                if (orderAmount.compareTo(coupon.getThresholdAmount()) < 0) {
                    throw new ServiceException(BusinessStatusEnum.COUPON_THRESHOLD_NOT_MET);
                }
                return coupon.getDiscountValue();

            case DISCOUNT:
                BigDecimal discount = BigDecimal.ONE.subtract(
                        coupon.getDiscountValue().divide(BigDecimal.TEN, 2, RoundingMode.HALF_UP));
                return orderAmount.multiply(discount).setScale(2, RoundingMode.HALF_UP);

            case NO_THRESHOLD:
                return coupon.getDiscountValue();

            default:
                throw new ServiceException(BusinessStatusEnum.COUPON_TYPE_UNKNOWN);
        }
    }

    @Override
    @Transactional
    public void lockUserCoupon(Integer couponId, Integer userId, Integer orderId) {
        int updated = userCouponMapper.update(null, new UpdateWrapper<UserCoupon>()
                .eq("coupon_id", couponId)
                .eq("user_id", userId)
                .eq("status", UserCouponStatusEnum.UNUSED)
                .set("status", UserCouponStatusEnum.LOCKED)
                .set("order_id", orderId)
                .set("update_time", LocalDateTime.now()));
        if (updated == 0) {
            throw new ServiceException(BusinessStatusEnum.COUPON_ALREADY_USED);
        }
    }

    @Override
    @Transactional
    public void releaseUserCoupon(Integer orderId) {
        userCouponMapper.update(null, new UpdateWrapper<UserCoupon>()
                .eq("order_id", orderId)
                .eq("status", UserCouponStatusEnum.LOCKED)
                .set("status", UserCouponStatusEnum.UNUSED)
                .set("order_id", null)
                .set("update_time", LocalDateTime.now()));
    }

    @Override
    @Transactional
    public void useUserCoupon(Integer orderId) {
        userCouponMapper.update(null, new UpdateWrapper<UserCoupon>()
                .eq("order_id", orderId)
                .eq("status", UserCouponStatusEnum.LOCKED)
                .set("status", UserCouponStatusEnum.USED)
                .set("use_time", LocalDateTime.now())
                .set("update_time", LocalDateTime.now()));
    }
}