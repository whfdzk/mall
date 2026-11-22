package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum CouponTypeEnum implements BaseEnum<Integer> {

    FULL_REDUCTION(1, "满减券"),
    DISCOUNT(2, "折扣券"),
    NO_THRESHOLD(3, "无门槛券");

    @JsonValue
    @EnumValue
    private final Integer code;
    private final String message;
}