package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.qiujie.validation.AddGroup;
import com.qiujie.validation.UpdateGroup;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;
import lombok.experimental.Accessors;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@Accessors(chain = true)
@TableName("oms_cart")
public class Cart {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    @TableField("user_id")
    private Integer userId;

    @NotNull(message = "商品ID不能为空", groups = AddGroup.class)
    @TableField("product_id")
    private Integer productId;

    @Min(value = 1, message = "数量至少为1", groups = {AddGroup.class, UpdateGroup.class})
    @TableField("amount")
    private Integer amount;

    @TableField("is_selected")
    private Integer isSelected;

    @TableField("create_time")
    private LocalDateTime createTime;

    @TableField("update_time")
    private LocalDateTime updateTime;

    @TableField(exist = false)
    private String productName;

    @TableField(exist = false)
    private BigDecimal productPrice;

    @TableField(exist = false)
    private String productImg;

    @TableField(exist = false)
    private Integer productStock;
}