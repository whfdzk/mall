package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum UserCouponStatusEnum implements BaseEnum<Integer> {

    UNUSED(0, "未使用"),
    LOCKED(1, "已锁定"),
    USED(2, "已使用"),
    EXPIRED(3, "已过期");

    @JsonValue
    @EnumValue
    private final Integer code;
    private final String message;
}