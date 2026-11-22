package com.qiujie.controller.internal;

import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.entity.Order;
import com.qiujie.exception.ServiceException;
import com.qiujie.service.OrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 内部-智能客服 Agent 接口。
 * <p>
 * 仅供 mall-customer（Python）服务端到服务端调用，通过 X-Internal-Token 鉴权，
 * 不走 Sa-Token 登录态（Agent 拿不到用户的登录 token，由 mall-server 用 user_id 代查）。
 *
 * @author whf
 */
@RestController
@RequestMapping("/internal/agent")
@Tag(name = "内部-智能客服Agent")
public class AgentOrderController {

    private final OrderService orderService;
    private final String internalToken;

    public AgentOrderController(OrderService orderService,
                                @Value("${mall.internal.token}") String internalToken) {
        this.orderService = orderService;
        this.internalToken = internalToken;
    }

    private void checkToken(String token) {
        if (internalToken == null || internalToken.isBlank() || !internalToken.equals(token)) {
            throw new ServiceException(401, "内部接口鉴权失败");
        }
    }

    @Operation(summary = "按用户ID查询订单列表（供 mall-customer Agent 调用）")
    @GetMapping("/order/list")
    public ResponseDTO<List<Order>> listOrders(
            @RequestParam Integer userId,
            @RequestHeader(value = "X-Internal-Token", required = false) String token) {
        checkToken(token);
        return Response.success(orderService.list(userId));
    }
}