CREATE TABLE IF NOT EXISTS sms_coupon (
    id int NOT NULL AUTO_INCREMENT,
    name varchar(100) NOT NULL,
    type tinyint NOT NULL,
    threshold_amount decimal(10,2) DEFAULT NULL,
    discount_value decimal(10,2) NOT NULL,
    total_stock int NOT NULL,
    per_limit int NOT NULL DEFAULT 1,
    start_time datetime NOT NULL,
    end_time datetime NOT NULL,
    description varchar(500) DEFAULT NULL,
    create_time datetime DEFAULT CURRENT_TIMESTAMP,
    update_time datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted tinyint DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_type (type),
    KEY idx_time (start_time, end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sms_user_coupon (
    id int NOT NULL AUTO_INCREMENT,
    user_id int NOT NULL,
    coupon_id int NOT NULL,
    status tinyint NOT NULL DEFAULT 0,
    order_id int DEFAULT NULL,
    use_time datetime DEFAULT NULL,
    create_time datetime DEFAULT CURRENT_TIMESTAMP,
    update_time datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted tinyint DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_coupon (user_id, coupon_id),
    KEY idx_user_id (user_id),
    KEY idx_coupon_id (coupon_id),
    KEY idx_order_id (order_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='mall' AND TABLE_NAME='oms_order' AND COLUMN_NAME='coupon_id';
SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='mall' AND TABLE_NAME='oms_order' AND COLUMN_NAME='discount_amount';
