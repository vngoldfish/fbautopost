import random

def handle_ai_route(path: str, method: str, body: dict = None) -> tuple:
    if path == "/api/ai/suggest-reply" and method == "POST":
        payload = body or {}
        comment_text = (payload.get("commentText") or "").strip()
        post_content = (payload.get("postContent") or "").strip()
        tone = (payload.get("tone") or "friendly").lower()
        
        cmt_lower = comment_text.lower()
        
        if tone == "sales":
            if any(k in cmt_lower for k in ["giá", "bao nhiêu", "báo giá", "nhiêu"]):
                templates = [
                    "Dạ em đã gửi bảng giá niêm yết kèm ưu đãi chốt đơn hôm nay qua inbox cho bạn rồi ạ! Bạn kiểm tra tin nhắn giúp shop nha! ❤️",
                    "Dạ mẫu này bên shop đang bán rất chạy ạ! Em vừa nhắn tin báo giá ưu đãi đặc biệt qua inbox cho mình rồi nhé! 🔥"
                ]
            else:
                templates = [
                    "Dạ chào bạn, shop đã inbox thông tin sản phẩm và chính sách giá tốt nhất cho bạn rồi ạ. Bạn kiểm tra tin nhắn nhé! ✨",
                    "Dạ shop vừa gửi thông tin chi tiết kèm mã ưu đãi đặt hàng qua inbox cho mình rồi nha! 💕"
                ]
        elif tone == "discount":
            templates = [
                "Dạ chào bạn! Shop dành tặng riêng cho bạn mã FREESHIP toàn quốc kèm quà tặng nhỏ khi chốt đơn hôm nay ạ. Bạn check inbox shop tư vấn nhé! 🎁",
                "Dạ em đã gửi mã giảm giá 10% độc quyền qua inbox cho mình rồi nha! Bạn kiểm tra tin nhắn giúp shop nhé! ✨"
            ]
        else: # friendly / sweet
            if any(k in cmt_lower for k in ["giá", "bao nhiêu", "báo giá", "nhiêu", "chi phí"]):
                templates = [
                    "Dạ chào bạn! Shop đã nhắn tin báo giá chi tiết kèm ưu đãi quà tặng qua inbox cho mình rồi ạ, bạn kiểm tra tin nhắn giúp shop nha! ❤️",
                    "Dạ mẫu này bên shop đang có chương trình trợ giá cực tốt ạ! Bạn check tin nhắn chờ inbox shop đã gửi bảng giá chi tiết cho mình rồi nhen! ✨"
                ]
            elif any(k in cmt_lower for k in ["ship", "vận chuyển", "giao hàng", "địa chỉ"]):
                templates = [
                    "Dạ shop hỗ trợ giao hàng tận nơi siêu tốc và được kiểm tra hàng trước khi thanh toán ạ! Em đã nhắn tin tư vấn qua inbox cho mình rồi nha! 🚚",
                    "Dạ shop có ship COD toàn quốc ạ. Bạn check inbox shop gửi thông tin giao hàng chi tiết nhé! 📦"
                ]
            else:
                templates = [
                    "Dạ em cảm ơn bạn đã quan tâm sản phẩm của shop ạ! Shop đã nhắn tin tư vấn chi tiết qua inbox cho mình rồi nha! ❤️",
                    "Dạ chào bạn, shop đã gửi lời tư vấn chi tiết qua inbox cho bạn rồi ạ. Bạn kiểm tra tin nhắn giúp shop nha! ✨"
                ]
            
        suggested = random.choice(templates)
        return 200, {"success": True, "suggestedReply": suggested, "commentText": comment_text, "tone": tone}

    return 404, {"error": "AI Route not found"}
