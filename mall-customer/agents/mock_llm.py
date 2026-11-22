import re
from langchain_core.messages import AIMessage


class MockLLM:
    """
    无 API Key 时的降级 LLM：基于规则匹配返回固定回复。
    实现 langchain 风格的 ainvoke，返回带 .content 的 AIMessage。
    """

    def __init__(self):
        self._call_count = 0

    async def ainvoke(self, messages, *args, **kwargs):
        self._call_count += 1
        last_text = ""
        for m in reversed(messages):
            if hasattr(m, "content") and m.content:
                last_text = m.content
                break
        if isinstance(messages, list) and messages:
            last_text = str(messages[-1]) if not last_text else last_text

        content = self._rule_based_reply(last_text)
        return AIMessage(content=content)

    def invoke(self, messages, *args, **kwargs):
        import asyncio
        return asyncio.run(self.ainvoke(messages, *args, **kwargs))

    def route_intent(self, text: str) -> str:
        """规则路由：返回 Supervisor 可识别的合法意图名。

        无 API Key 降级时，Supervisor 不再依赖 LLM 的意图输出，
        而是用本方法按关键词分流，保证 chitchat / ticket_handler /
        compliance_checker 等子 Agent 依然可达。
        """
        import re

        t = text.lower()
        if not t:
            return "chitchat"

        # 中文关键词用子串匹配；英文用整词匹配，避免 "hi" 命中 "this" 之类误判
        def has_zh(kw: str) -> bool:
            return kw in text

        def has_en(kw: str) -> bool:
            return re.search(rf"\b{re.escape(kw)}\b", t) is not None

        # 顺序即优先级：先匹配高风险/强诉求，再匹配业务办理，最后才是闲聊与兜底
        kw_compliance_zh = ["被盗", "盗刷", "诈骗", "欺诈", "举报", "资金安全", "账户异常", "洗钱"]
        kw_ticket_zh = ["退款", "退货", "退钱", "理赔", "开户", "投诉", "差评", "加急", "办理", "工单"]
        kw_ticket_en = ["refund"]
        kw_order_zh = ["订单", "快递", "物流", "发货", "收货", "订单号", "包裹", "查单"]
        kw_order_en = ["order", "ship", "track"]
        kw_chitchat_zh = ["你好", "您好", "在吗", "你是谁", "谢谢", "感谢", "再见", "拜拜", "早上好", "晚上好", "辛苦"]
        kw_chitchat_en = ["hi", "hello", "hey"]

        if any(has_zh(k) for k in kw_compliance_zh):
            return "compliance_checker"
        if any(has_zh(k) for k in kw_ticket_zh) or any(has_en(k) for k in kw_ticket_en):
            return "ticket_handler"
        if any(has_zh(k) for k in kw_order_zh) or any(has_en(k) for k in kw_order_en):
            return "order_query"
        if any(has_zh(k) for k in kw_chitchat_zh) or any(has_en(k) for k in kw_chitchat_en):
            return "chitchat"
        return "knowledge_rag"

    def _rule_based_reply(self, text: str) -> str:
        t = text.lower()
        if not t or len(t) < 2:
            return "您好！我是 Mall 智能客服，很高兴为您服务。您可以咨询商品、退款、下单等问题哦～"

        kw_deal = ["退款", "退货", "退钱", "refund"]
        kw_product = ["商品", "产品", "多少钱", "价格", "有货", "stock"]
        kw_order = ["订单", "下单", "快递", "物流", "发货", "order", "ship"]
        kw_account = ["注册", "登录", "开户", "账号", "密码"]
        kw_ticket = ["投诉", "差评", "问题"]
        kw_hello = ["你好", "您好", "hi", "hello", "在吗", "你是谁"]

        for kw in kw_deal:
            if kw in t or kw in text:
                return "退款政策：用户购买后 7 天内可申请无理由退款，超过 7 天需提供合理原因。退款将在 1-5 个工作日内原路退回。请问您的订单号是多少？"

        for kw in kw_product:
            if kw in t or kw in text:
                return "我们商城主打仿真花、花瓶、靠垫抱枕、香薰等创意家居用品。每件商品都有详细的规格参数和图片展示，您可以在商品详情页查看。需要我帮您介绍哪款商品？"

        for kw in kw_order:
            if kw in t or kw in text:
                return "下单流程：1. 选商品加入购物车 2. 去结算 3. 填写收货地址 4. 选择支付方式 5. 确认付款。一般 24 小时内发货，支持顺丰包邮。请问您有订单相关的问题吗？"

        for kw in kw_account:
            if kw in t or kw in text:
                return "开户流程：1. 准备身份证原件 2. 填写开户申请表 3. 进行视频认证 4. 设置交易密码 5. 完成风险评估问卷。整体约 15-30 分钟。需要帮助吗？"

        for kw in kw_ticket:
            if kw in t or kw in text:
                return "很抱歉给您带来不好的体验！我已为您创建工单（Ticket#T-{:04d}），客服专员将在 2 小时内与您联系处理。".format(abs(hash(text)) % 10000)

        for kw in kw_hello:
            if kw in t or kw in text:
                return "您好！我是 Mall 智能客服小助手 🌸 可以帮您解答商品咨询、订单查询、退款政策、开户流程等问题。"

        return f"我理解您想了解「{text[:30]}」。关于这个问题，建议您可以联系人工客服或查看帮助中心。同时我也可以帮您查询商品、订单、退款等常见问题～"