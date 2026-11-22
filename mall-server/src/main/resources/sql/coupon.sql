-- ========== 优惠券系统建表 SQL ==========

CREATE TABLE IF NOT EXISTS sms_coupon (
    id int NOT NULL AUTO_INCREMENT COMMENT '主键',
    name varchar(100) NOT NULL COMMENT '优惠券名称',
    type tinyint NOT NULL COMMENT '优惠券类型：1-满减券 2-折扣券 3-无门槛券',
    threshold_amount decimal(10,2) DEFAULT NULL COMMENT '使用门槛金额（满减券必填）',
    discount_value decimal(10,2) NOT NULL COMMENT '优惠金额（满减/无门槛）或折扣值（如8表示8折）',
    total_stock int NOT NULL COMMENT '发放总量',
    per_limit int NOT NULL DEFAULT 1 COMMENT '每人限领数量',
    start_time datetime NOT NULL COMMENT '生效开始时间',
    end_time datetime NOT NULL COMMENT '生效结束时间',
    description varchar(500) DEFAULT NULL COMMENT '使用说明',
    create_time datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted tinyint DEFAULT 0 COMMENT '逻辑删除：0-未删除 1-已删除',
    PRIMARY KEY (id),
    KEY idx_type (type),
    KEY idx_time (start_time, end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='优惠券模板表';

CREATE TABLE IF NOT EXISTS sms_user_coupon (
    id int NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id int NOT NULL COMMENT '用户ID',
    coupon_id int NOT NULL COMMENT '优惠券模板ID',
    status tinyint NOT NULL DEFAULT 0 COMMENT '状态：0-未使用 1-已锁定 2-已使用 3-已过期',
    order_id int DEFAULT NULL COMMENT '关联订单ID（使用时关联）',
    use_time datetime DEFAULT NULL COMMENT '使用时间',
    create_time datetime DEFAULT CURRENT_TIMESTAMP COMMENT '领取时间',
    update_time datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    is_deleted tinyint DEFAULT 0 COMMENT '逻辑删除：0-未删除 1-已删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_coupon (user_id, coupon_id),
    KEY idx_user_id (user_id),
    KEY idx_coupon_id (coupon_id),
    KEY idx_order_id (order_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户优惠券实例表';

ALTER TABLE oms_order ADD COLUMN IF NOT EXISTS coupon_id int DEFAULT NULL COMMENT '使用的优惠券ID' AFTER pay_method;
ALTER TABLE oms_order ADD COLUMN IF NOT EXISTS discount_amount decimal(10,2) DEFAULT 0 COMMENT '优惠券优惠金额' AFTER coupon_id;

INSERT INTO sms_coupon (name, type, threshold_amount, discount_value, total_stock, per_limit, start_time, end_time, description) VALUES
('新用户满100减20', 1, 100.00, 20.00, 1000, 1, DATE_ADD(NOW(), INTERVAL -1 DAY), DATE_ADD(NOW(), INTERVAL 30 DAY), '新用户专享，满100元可用'),
('全场8折券', 2, NULL, 8.00, 500, 2, DATE_ADD(NOW(), INTERVAL -1 DAY), DATE_ADD(NOW(), INTERVAL 7 DAY), '全场商品8折优惠'),
('无门槛10元券', 3, NULL, 10.00, 2000, 1, DATE_ADD(NOW(), INTERVAL -1 DAY), DATE_ADD(NOW(), INTERVAL 14 DAY), '无门槛，直接减10元');
