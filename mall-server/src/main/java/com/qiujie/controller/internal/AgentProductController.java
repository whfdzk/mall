package com.qiujie.controller.internal;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.entity.Category;
import com.qiujie.entity.Product;
import com.qiujie.enums.ProductStatusEnum;
import com.qiujie.exception.ServiceException;
import com.qiujie.mapper.CategoryMapper;
import com.qiujie.service.ProductAdminService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 内部-智能客服 Agent 接口（商品知识库）。
 * <p>
 * 供 mall-customer（Python）在启动时拉取真实上架商品，构建 RAG 知识库。
 * 同样走 X-Internal-Token 服务间鉴权，避免接口裸奔。
 *
 * @author qiujie
 */
@RestController
@RequestMapping("/internal/agent")
@Tag(name = "内部-智能客服Agent")
public class AgentProductController {

    private final ProductAdminService productAdminService;
    private final CategoryMapper categoryMapper;
    private final String internalToken;

    public AgentProductController(ProductAdminService productAdminService,
                                  CategoryMapper categoryMapper,
                                  @Value("${mall.internal.token}") String internalToken) {
        this.productAdminService = productAdminService;
        this.categoryMapper = categoryMapper;
        this.internalToken = internalToken;
    }

    private void checkToken(String token) {
        if (internalToken == null || internalToken.isBlank() || !internalToken.equals(token)) {
            throw new ServiceException(401, "内部接口鉴权失败");
        }
    }

    @Operation(summary = "上架商品列表（供 mall-customer Agent 构建知识库）")
    @GetMapping("/product/list")
    public ResponseDTO<List<Map<String, Object>>> listProducts(
            @RequestHeader(value = "X-Internal-Token", required = false) String token) {
        checkToken(token);

        List<Product> products = productAdminService.list(
                new QueryWrapper<Product>().eq("status", ProductStatusEnum.ON_SHELF));

        Map<Integer, String> categoryNames = new HashMap<>();
        for (Category c : categoryMapper.selectList(
                new QueryWrapper<Category>().eq("is_deleted", 0))) {
            categoryNames.put(c.getId(), c.getName());
        }

        List<Map<String, Object>> result = new ArrayList<>();
        for (Product p : products) {
            Map<String, Object> item = new HashMap<>();
            item.put("id", p.getId());
            item.put("name", p.getName());
            item.put("price", p.getPrice());
            item.put("categoryId", p.getCategoryId());
            item.put("categoryName", categoryNames.get(p.getCategoryId()));
            item.put("detail", p.getDetail());
            result.add(item);
        }
        return Response.success(result);
    }
}