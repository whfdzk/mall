package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.qiujie.enums.CouponTypeEnum;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;
import lombok.experimental.Accessors;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@Accessors(chain = true)
@TableName("sms_coupon")
public class Coupon {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    @NotBlank(message = "优惠券名称不能为空")
    @TableField("name")
    private String name;

    @NotNull(message = "优惠券类型不能为空")
    @TableField("type")
    private CouponTypeEnum type;

    @TableField("threshold_amount")
    private BigDecimal thresholdAmount;

    @NotNull(message = "优惠金额/折扣不能为空")
    @TableField("discount_value")
    private BigDecimal discountValue;

    @NotNull(message = "发放总量不能为空")
    @TableField("total_stock")
    private Integer totalStock;

    @NotNull(message = "每人限领数量不能为空")
    @TableField("per_limit")
    private Integer perLimit;

    @NotNull(message = "生效开始时间不能为空")
    @TableField("start_time")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime startTime;

    @NotNull(message = "生效结束时间不能为空")
    @TableField("end_time")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime endTime;

    @TableField("description")
    private String description;

    @TableField("create_time")
    private LocalDateTime createTime;

    @TableField("update_time")
    private LocalDateTime updateTime;

    @TableField("is_deleted")
    @TableLogic
    private Integer deleted;
}