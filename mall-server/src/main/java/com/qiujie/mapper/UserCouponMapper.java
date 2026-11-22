package com.qiujie.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.entity.UserCoupon;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface UserCouponMapper extends BaseMapper<UserCoupon> {

    @Select("SELECT uc.*, c.name AS coupon_name, c.type AS coupon_type, " +
            "c.threshold_amount, c.discount_value, c.start_time AS coupon_start_time, c.end_time AS coupon_end_time " +
            "FROM sms_user_coupon uc LEFT JOIN sms_coupon c ON uc.coupon_id = c.id " +
            "WHERE uc.user_id = #{userId} AND uc.is_deleted = 0 " +
            "ORDER BY uc.create_time DESC")
    IPage<UserCoupon> selectUserCouponsWithDetail(Page<UserCoupon> page, @Param("userId") Integer userId);
}