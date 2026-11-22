package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.qiujie.enums.UserCouponStatusEnum;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

@Data
@Accessors(chain = true)
@TableName("sms_user_coupon")
public class UserCoupon {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    @TableField("user_id")
    private Integer userId;

    @TableField("coupon_id")
    private Integer couponId;

    @TableField("status")
    private UserCouponStatusEnum status;

    @TableField("order_id")
    private Integer orderId;

    @TableField("use_time")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime useTime;

    @TableField("create_time")
    private LocalDateTime createTime;

    @TableField("update_time")
    private LocalDateTime updateTime;

    @TableField("is_deleted")
    @TableLogic
    private Integer deleted;

    @TableField(exist = false)
    private String couponName;

    @TableField(exist = false)
    private Integer couponType;

    @TableField(exist = false)
    private java.math.BigDecimal thresholdAmount;

    @TableField(exist = false)
    private java.math.BigDecimal discountValue;

    @TableField(exist = false)
    private LocalDateTime couponStartTime;

    @TableField(exist = false)
    private LocalDateTime couponEndTime;
}