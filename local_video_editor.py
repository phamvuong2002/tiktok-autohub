# -*- coding: utf-8 -*-
"""
NEW LIVEVAULT LINK BATCH FETCHER, AI VIETNAMESE TRANSCRIBER & FFMPEG TIKTOK PILL EDITOR
Cho phep nguoi dung dan BAT KY link thu video LiveVault moi nao (vd: http://192.168.1.75:8090/d/... hoac http://127.0.0.1:8090/d/...)
ngay tren giao dien http://127.0.0.1:8099 de:
1. Tu dong chuyen doi IP trong link LiveVault ve http://127.0.0.1:8090 (dich vu tiktok_recorder dang chay ngay tren Laptop)
2. Quet danh sach clip .mp4 moi nhat trong link LiveVault do (hoac 1 clip cu the neu link co ?clip=...)
3. Kiem tra So cai Chong Dang Trung 4 Lop (anti_duplicate_ledger.db) -> Bo qua 100% cac clip da tung dang/luu nhap
4. Nhan dien giong noi Tieng Viet (vi-VN) -> Tu dong phat hien san pham Bac Chuong dang tu van & cat bo doan cuoi vi pham (Lazada/bao gia)
5. Dung FFmpeg + PIL (Font Arial Bold Tieng Viet Unicode) tren Laptop (hoac giao R630 neu dang bat Cau noi):
   - Xoa vien tim tren/duoi + Xoa logo do LiveVault (delogo)
   - Dao 3.5 giay Hook len dau (00:00)
   - Dong khung chu Vang chu Den 3-4 dong gon chuan TikTok Pill (le an toan >= 110px)
   - Unique hoa 2 ban rieng biet cho @suckhoeviet.2 va @suc.khoe.vang.268
   - Sinh Caption Tieng Viet CO DAU 100% + 5 Hashtag chuan SEO + Shop ID GMV Max
   - Dua thang loat video moi nay len DAU bang Lich Dang 1 Tieng / 1 Video!
"""
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from anti_dup_sync import (
    ALLOWED_CHANNELS,
    CACHE_DIR,
    DATA_DIR,
    DB_PATH,
    HUB_DIR,
    LOCAL_QUEUE_FILE,
    init_db,
)

FFMPEG_EXE = r"C:\ffmpeg\bin\ffmpeg.exe" if Path(r"C:\ffmpeg\bin\ffmpeg.exe").exists() else "ffmpeg"
RAW_TMP_DIR = DATA_DIR / "raw_livevault_tmp"
RAW_TMP_DIR.mkdir(parents=True, exist_ok=True)

EDITOR_STATUS = {
    "is_running": False,
    "progress_text": "Sẵn sàng nhận link thu mới (LiveVault /d/... hoặc link TikTok Live) để tự động cắt, edit & đẩy Lưu Nháp lên Oppo A57.",
    "current_step": "Sẵn sàng nhận link thu mới để chạy tự động toàn trình.",
    "progress_pct": 0,
    "processed_clips": 0,
    "total_clips": 0,
    "created_videos": 0,
    "last_link": "",
}


def set_editor_progress(text: str, pct: int = None):
    EDITOR_STATUS["progress_text"] = text
    EDITOR_STATUS["current_step"] = text
    if pct is not None:
        EDITOR_STATUS["progress_pct"] = max(0, min(100, int(pct)))

PRODUCT_CATALOG = {
    "bokhop_chondro": {
        "keywords": ["khớp", "sụn", "đầu gối", "lụp cụp", "thoái hóa", "chondro", "glucosamine", "xương"],
        "product_name": "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp (Hỗ trợ sụn khớp, giảm khô khớp)",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505842",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Bổ Khớp Chondro-Aid Pháp", "Bổ sung Glucosamine & Sụn", "Khô khớp, kêu lụp cụp", "Ngày 2 viên sau bữa ăn"],
                "caption_seo": (
                    "Khô khớp, cứng khớp, khớp gối kêu lụp cụp mỗi khi vận động\n"
                    "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp — Bổ sung Glucosamine giúp hỗ trợ bôi trơn sụn khớp và đi lại linh hoạt.\n"
                    "👉 Bấm vào giỏ hàng góc trái màn hình để xem ưu đãi chính hãng!\n"
                    "#arkopharma #chondroaid #bokhop #glucosamine #xuongkhop"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Viên Uống Bổ Khớp Pháp", "Hỗ trợ khô khớp, mỏi gối", "Đứng lên ngồi xuống khó", "Sáng 1 viên - Chiều 1 viên"],
                "caption_seo": (
                    "Đứng lên ngồi xuống khó khăn, đau mỏi khớp gối khi lên xuống cầu thang\n"
                    "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp — Hỗ trợ dưỡng khớp êm ái, vận động nhẹ nhàng cho người lớn tuổi.\n"
                    "👉 Xem ngay tại giỏ hàng màu vàng góc trái video!\n"
                    "#bokhop #duongkhop #chondroaid #khopgoi #chamsocsuckhoe"
                ),
            },
        },
    },
    "daday_baotu": {
        "keywords": ["marial", "mi đen", "mang gen", "malaysia", "dạ dày", "bao tử", "ngang ngực", "tức ngực", "ợ chua", "ợ hơi", "trào ngược", "đau rát", "ăn chua", "xé uống liền", "xé ra uống", "viêm xung huyết"],
        "product_name": "Hỗn dịch dạ dày & trào ngược Marial Gel Ý (Hộp 20 gói uống liền)",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Chăm Sóc Sức Khỏe Chính Hãng (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505890",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Hỗn dịch dạ dày Marial Gel", "Hỗ trợ trào ngược, đau bao tử", "Ăn xong ngang ngực, ợ chua", "Dạng gói xé uống liền tiện lợi"],
                "caption_seo": (
                    "Đau rát dạ dày, ăn xong ngang ngực, ợ hơi ợ chua, trào ngược thực quản\n"
                    "Hỗn dịch dạ dày & trào ngược Marial Gel Ý — Hỗ trợ làm dịu nhanh niêm mạc dạ dày & thực quản, giảm nóng rát khó chịu.\n"
                    "Cách dùng: Xé uống liền 1 gói sau ăn hoặc khi đau rát\n"
                    "#marialgel #traonguocdaday #daudaday #baotu #chamsocsuckhoe"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Marial Gel — Bảo vệ Bao Tử", "Giảm ợ hơi, ợ chua, nóng rát", "Đau dạ dày ban đêm khó ngủ", "1 gói sau ăn hoặc khi khó chịu"],
                "caption_seo": (
                    "Hay đau bao tử thất thường vào ban đêm, nóng rát cổ họng do trào ngược\n"
                    "Hỗn dịch dạ dày & trào ngược Marial Gel Ý — Dạng gói hỗn dịch uống liền giúp bảo vệ niêm mạc bao tử êm ái.\n"
                    "Cách dùng: Xé uống liền 1 gói sau ăn hoặc khi khó chịu\n"
                    "#marialgel #baotu #traonguoc #daudaday #suckhoegiadinh"
                ),
            },
        },
    },
    "marial_gel": {
        "keywords": ["marial", "mi đen", "mang gen", "malaysia", "dạ dày", "bao tử", "ngang ngực", "tức ngực", "ợ chua", "ợ hơi", "trào ngược", "đau rát", "ăn chua", "xé uống liền", "xé ra uống", "viêm xung huyết"],
        "product_name": "Hỗn dịch dạ dày & trào ngược Marial Gel Ý (Hộp 20 gói uống liền)",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Chăm Sóc Sức Khỏe Chính Hãng (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505890",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Hỗn dịch dạ dày Marial Gel", "Hỗ trợ trào ngược, đau bao tử", "Ăn xong ngang ngực, ợ chua", "Dạng gói xé uống liền tiện lợi"],
                "caption_seo": (
                    "Đau rát dạ dày, ăn xong ngang ngực, ợ hơi ợ chua, trào ngược thực quản\n"
                    "Hỗn dịch dạ dày & trào ngược Marial Gel Ý — Hỗ trợ làm dịu nhanh niêm mạc dạ dày & thực quản, giảm nóng rát khó chịu.\n"
                    "Cách dùng: Xé uống liền 1 gói sau ăn hoặc khi đau rát\n"
                    "#marialgel #traonguocdaday #daudaday #baotu #chamsocsuckhoe"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Marial Gel — Bảo vệ Bao Tử", "Giảm ợ hơi, ợ chua, nóng rát", "Đau dạ dày ban đêm khó ngủ", "1 gói sau ăn hoặc khi khó chịu"],
                "caption_seo": (
                    "Hay đau bao tử thất thường vào ban đêm, nóng rát cổ họng do trào ngược\n"
                    "Hỗn dịch dạ dày & trào ngược Marial Gel Ý — Dạng gói hỗn dịch uống liền giúp bảo vệ niêm mạc bao tử êm ái.\n"
                    "Cách dùng: Xé uống liền 1 gói sau ăn hoặc khi khó chịu\n"
                    "#marialgel #baotu #traonguoc #daudaday #suckhoegiadinh"
                ),
            },
        },
    },
    "ginkgo_bonao": {
        "keywords": ["ginkgo", "ganko", "bổ não", "dưỡng não", "tiền đình", "rối loạn tiền đình", "tuần hoàn não", "hoa mắt", "chóng mặt", "ù tai", "đau đầu"],
        "product_name": "Viên uống dưỡng não Ginkgo Biloba Mỹ (Hộp 60 viên)",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Mason Natural / Olympian Labs (GMV Max - isAd: TRUE)",
        "product_id": "1731468745270135099",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Dưỡng não Ginkgo Biloba Mỹ", "Hỗ trợ tuần hoàn máu não", "Hoa mắt, chóng mặt, tiền đình", "Ngày uống 1 viên sau ăn"],
                "caption_seo": (
                    "Đau đầu, hoa mắt, chóng mặt, ù tai, mất ngủ do thiểu năng tuần hoàn não\n"
                    "Viên uống dưỡng não Ginkgo Biloba Mỹ — Hỗ trợ tăng cường tuần hoàn máu não, cải thiện rối loạn tiền đình.\n"
                    "Cách dùng: Ngày uống 1 viên sau ăn\n"
                    "#ginkgobiloba #duongnao #tuanhoannao #roiloantiendinh #chamsocsuckhoe"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Hay đau đầu, mất ngủ, ù tai", "Rối loạn tiền đình, chóng mặt", "Viên uống Dưỡng Não từ Mỹ", "1 viên/ngày, hộp dùng 2 tháng"],
                "caption_seo": (
                    "Người lớn tuổi hay chóng mặt quay cuồng, đau nửa đầu, đêm khó ngủ\n"
                    "Viên uống dưỡng não Ginkgo Biloba Mỹ — Bổ sung Ginkgo Biloba chuẩn Mỹ hỗ trợ máu lưu thông lên não tốt hơn.\n"
                    "Cách dùng: Ngày uống 1 viên sau ăn\n"
                    "#bonao #ginkgobiloba #tiendinh #matngu #baovesuckhoe"
                ),
            },
        },
    },
    "vitamin_azinc": {
        "keywords": ["vitamin tổng hợp", "azinc", "adc", "3b", "b1 b6 b12", "dây thần kinh tọa", "thiếu máu", "thiếu sắt", "120 viên", "12 vitamin", "ăn chay"],
        "product_name": "Vitamin tổng hợp Azinc Arkopharma Pháp (12 Vitamin & 8 Khoáng chất - 120 viên)",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1729632607717722546",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Vitamin tổng hợp Azinc Pháp", "12 Vitamin & 8 Khoáng chất", "Mệt mỏi, tê tay chân, ăn chay", "2 viên/ngày sau bữa ăn sáng"],
                "caption_seo": (
                    "Thường xuyên mệt mỏi, uể oải, tê mỏi tay chân, ăn chay hoặc mới ốm dậy thiếu vi chất\n"
                    "Vitamin tổng hợp Azinc Arkopharma Pháp — Bổ sung 12 Vitamin (có 3B B1-B6-B12) & 8 Khoáng chất (Sắt, Kẽm, Canxi) hỗ trợ bồi bổ sức khỏe.\n"
                    "Cách dùng: Ngày 2 viên buổi sáng sau ăn\n"
                    "#arkopharma #vitamintonghop #azinc #tangdekhang #chamsocsuckhoe"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Bồi bổ cơ thể, giảm mệt mỏi", "Đủ 20 Vitamin & Khoáng chất", "Có nhóm 3B, Sắt, Kẽm từ Pháp", "Ngày uống 2 viên buổi sáng"],
                "caption_seo": (
                    "Hay ốm vặt khi đổi mùa, ăn uống kém ngon miệng, cơ thể suy nhược thiếu chất\n"
                    "Vitamin tổng hợp Azinc Arkopharma Pháp — Hỗ trợ tăng cường sức đề kháng cho người từ 15 tuổi trở lên và người lớn tuổi.\n"
                    "Cách dùng: Ngày 2 viên buổi sáng sau ăn\n"
                    "#vitamintonghop #multivitamin #tangcuongsuckhoe #arkopharma #vitamin"
                ),
            },
        },
    },
    "biotin_forcapil": {
        "keywords": ["rụng tóc", "mọc tóc", "biotin", "forcapil", "for cabin", "ford cabin", "dưỡng tóc", "mái tóc", "tóc khô", "gãy rụng"],
        "product_name": "Viên uống dưỡng tóc Biotin Pháp Arkopharma Forcapil (Hộp 60 viên)",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1729569737652668850",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Dưỡng tóc Biotin Pháp", "Tóc yếu hay gãy rụng", "Tóc con mọc chắc khỏe", "Ngày 2 viên buổi sáng"],
                "caption_seo": (
                    "Tóc khô xơ, dễ gãy rụng khi gội đầu, rụng tóc nhiều ở phụ nữ sau sinh hoặc tiền mãn kinh\n"
                    "Viên uống dưỡng tóc Biotin Pháp Arkopharma Forcapil — Bổ sung Biotin, Kẽm & Vitamin nhóm B từ Pháp hỗ trợ tóc chắc khỏe.\n"
                    "Cách dùng: Ngày 2 viên buổi sáng sau ăn\n"
                    "#forcapil #rungtocsausinh #rungtoc #arkopharma #biotin"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Giảm gãy rụng tóc, mọc tóc", "Tóc mỏng, móng dễ gãy", "Biotin Forcapil từ Pháp", "Ngày 2 viên sau ăn sáng"],
                "caption_seo": (
                    "Tóc thưa mỏng, gãy rụng nhiều mỗi khi chải đầu hoặc gội đầu\n"
                    "Viên uống dưỡng tóc Biotin Pháp Arkopharma Forcapil — Hỗ trợ nuôi dưỡng nang tóc và móng khỏe mạnh từ bên trong.\n"
                    "Cách dùng: Ngày 2 viên buổi sáng sau ăn\n"
                    "#duongtoc #biotin #forcapil #arkopharma #rungtoc"
                ),
            },
        },
    },
    "giaidoc_gan": {
        "keywords": ["gan", "men gan", "mề đay", "mẩn ngứa", "nóng trong", "bia rượu", "đắng miệng"],
        "product_name": "Viên uống Giải Độc Gan & Hỗ Trợ Hạ Men Gan Chính Hãng (GMV Max)",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Mason & Chăm Sóc Sức Khỏe (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505844",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Giải Độc Gan & Mát Gan", "Nóng trong, mẩn ngứa mề đay", "Hỗ trợ hạ men gan cao", "Bảo vệ tế bào gan mỗi ngày"],
                "caption_seo": (
                    "Nóng trong người, mẩn ngứa mề đay, men gan cao do bia rượu hoặc dùng thuốc tây\n"
                    "Bác Chường tư vấn cách thanh nhiệt, giải độc và bảo vệ tế bào gan khỏe mạnh mỗi ngày.\n"
                    "👉 Xem chi tiết tại giỏ hàng góc trái màn hình!\n"
                    "#giaidocgan #mengancao #matgan #medaymanngua #suckhoegan"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Thảo Dược Bảo Vệ Lá Gan", "Giảm mẩn ngứa, nóng gan", "Đắng miệng, mệt mỏi uể oải", "Thanh nhiệt mát gan an toàn"],
                "caption_seo": (
                    "Dấu hiệu cảnh báo gan đang quá tải: Mẩn ngứa, nổi mề đay, đắng miệng, mệt mỏi\n"
                    "Giải pháp thảo dược hỗ trợ mát gan, tăng cường chức năng gan an toàn từ Bác Chường.\n"
                    "👉 Bấm vào giỏ hàng màu vàng góc trái để nhận ưu đãi!\n"
                    "#baovegan #thanhnhietmatgan #giaidocgan #suckhoemoingay #suckhoevang"
                ),
            },
        },
    },
    "matngu_bonao": {
        "keywords": ["mất ngủ", "khó ngủ", "trằn trọc", "tiền đình", "đau đầu", "chóng mặt", "tuần hoàn não"],
        "product_name": "Viên uống Hỗ Trợ Giấc Ngủ & Tuần Hoàn Máu Não Chính Hãng (GMV Max)",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505845",
        "variants": {
            "@suckhoeviet.2": {
                "cover_lines": ["Hỗ Trợ Ngủ Ngon Sâu Giấc", "Trằn trọc, đêm thức nhiều lần", "Tăng cường tuần hoàn não", "Sáng dậy tỉnh táo nhẹ người"],
                "caption_seo": (
                    "Trằn trọc khó vào giấc, đêm thức giấc nhiều lần, sáng dậy mệt mỏi uể oải\n"
                    "Bác Chường chia sẻ giải pháp dưỡng tâm an thần, hỗ trợ tuần hoàn máu não giúp ngủ sâu giấc tự nhiên.\n"
                    "👉 Tham khảo ngay tại giỏ hàng góc trái màn hình!\n"
                    "#matngu #khongu #tuanhoannao #giacngungon #suckhoeviet"
                ),
            },
            "@suc.khoe.vang.268": {
                "cover_lines": ["Dưỡng Não & An Thần Tự Nhiên", "Giảm hoa mắt, chóng mặt", "Mất ngủ kinh niên ở người già", "Ngủ sâu giấc không mệt mỏi"],
                "caption_seo": (
                    "Người lớn tuổi hay mất ngủ ban đêm, đau đầu hoa mắt chóng mặt khi thay đổi thời tiết\n"
                    "Cùng nghe Bác Chường tư vấn cách chăm sóc giấc ngủ sâu, tinh thần minh mẫn mỗi ngày.\n"
                    "👉 Bấm vào giỏ hàng góc trái để đặt mua chính hãng!\n"
                    "#ngungon #duongnao #matngukinhnien #chamsocnguoicaotuoi #suckhoevang"
                ),
            },
        },
    },
}


def normalize_livevault_url(raw_url: str) -> str:
    """Chuyen bat ky IP LAN nao tren cong 8090 ve http://127.0.0.1:8090 neu LiveVault dang chay tren Laptop."""
    raw_url = raw_url.strip()
    return re.sub(r"^https?://[^/:]+:8090", "http://127.0.0.1:8090", raw_url)


def create_yellow_pill_overlay_png(lines: list[str], out_png: Path):
    """Tao anh PNG trong suot 720x1280 chua 3-4 thanh Pill Nen Vang (#FDE047) Chu Den Dam co dau Tieng Viet (Le an toan >= 110px)."""
    W, H = 720, 1280
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = r"C:\Windows\Fonts\arialbd.ttf"
    if not Path(font_path).exists():
        font_path = r"C:\Windows\Fonts\segoeui.ttf"

    MAX_TEXT_W = 490  # Dam bao le trai/phai >= 115px, khong bao gio tran chu!
    y_cursor = 735
    for idx, line in enumerate(lines[:4]):
        line = line.strip()
        if not line:
            continue
        fsize = 30 if idx == 0 else 26
        font = ImageFont.truetype(font_path, fsize)
        while fsize > 18:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            if tw <= MAX_TEXT_W:
                break
            fsize -= 2
            font = ImageFont.truetype(font_path, fsize)

        bbox = draw.textbbox((0, 0), line, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad_x, pad_y = 20, 10
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        x1 = (W - box_w) // 2
        y1 = y_cursor
        x2 = x1 + box_w
        y2 = y1 + box_h

        # Bong do nhe + Hop pill nen vang vien den
        draw.rounded_rectangle([x1 + 3, y1 + 4, x2 + 3, y2 + 4], radius=16, fill=(0, 0, 0, 160))
        fill_color = (253, 224, 71, 248) if idx == 0 else (254, 240, 138, 242)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=16, fill=fill_color, outline=(15, 23, 42, 255), width=3)
        draw.text((x1 + pad_x, y1 + pad_y - bbox[1]), line, font=font, fill=(10, 10, 10, 255))
        y_cursor = y2 + 9

    img.save(str(out_png), "PNG")


def transcribe_and_detect_product(mp4_path: Path, forced_product_key: str = "AUTO") -> tuple[str, str, float]:
    """Nhan dien giong noi Tieng Viet trong clip de chon dung san pham va tim diem cat duoi vi pham."""
    transcript_parts = []
    safe_end_sec = 53.5
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        wav_tmp = RAW_TMP_DIR / "chunk_tmp.wav"
        for start_s in range(0, 54, 12):
            subprocess.run(
                [
                    FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(start_s), "-t", "11", "-i", str(mp4_path),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav_tmp),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
            )
            if wav_tmp.exists():
                with sr.AudioFile(str(wav_tmp)) as src:
                    audio = recognizer.record(src)
                try:
                    txt = recognizer.recognize_google(audio, language="vi-VN")
                    transcript_parts.append(f"[{start_s:02d}s]: {txt}")
                    low = txt.lower()
                    if start_s >= 36 and any(w in low for w in ["lazada", "shopee", "màn hình", "ngàn", "nghìn"]):
                        safe_end_sec = min(safe_end_sec, float(start_s))
                except Exception:
                    pass
    except Exception:
        pass

    full_tr = " | ".join(transcript_parts)
    if forced_product_key and forced_product_key in PRODUCT_CATALOG:
        return forced_product_key, full_tr, safe_end_sec

    low_tr = full_tr.lower()
    best_key = "bokhop_chondro"
    best_hits = 0
    for pkey, pinfo in PRODUCT_CATALOG.items():
        hits = sum(1 for kw in pinfo["keywords"] if kw in low_tr)
        if hits > best_hits:
            best_hits = hits
            best_key = pkey
    return best_key, full_tr, safe_end_sec


def render_single_channel_video(
    raw_mp4: Path,
    overlay_png: Path,
    out_mp4: Path,
    hook_start: float,
    body_start: float,
    body_end: float,
    zoom: float,
    speed: float,
) -> bool:
    """Cat Hook 3.5s + Than sach, xoa khung tim, delogo chu do va dong khung chu Vang chu Den."""
    body_dur = max(18.0, body_end - body_start)
    crop_h = int(1120 / zoom)
    crop_w = int(720 / zoom)
    crop_x = (720 - crop_w) // 2
    crop_y = 80 + (1120 - crop_h) // 2
    atempo = f",atempo={speed:.2f}" if abs(speed - 1.0) > 0.005 else ""
    setpts = f"*{1.0/speed:.4f}" if abs(speed - 1.0) > 0.005 else ""

    fc = (
        f"[0:v]trim=start={hook_start}:duration=3.5,setpts=(PTS-STARTPTS){setpts},"
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=720:1280,"
        f"delogo=x=85:y=792:w=560:h=56[vh];"
        f"[0:a]atrim=start={hook_start}:duration=3.5,asetpts=PTS-STARTPTS{atempo}[ah];"
        f"[0:v]trim=start={body_start}:duration={body_dur:.1f},setpts=(PTS-STARTPTS){setpts},"
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=720:1280,"
        f"delogo=x=85:y=792:w=560:h=56[vb];"
        f"[0:a]atrim=start={body_start}:duration={body_dur:.1f},asetpts=PTS-STARTPTS{atempo}[ab];"
        f"[vh][ah][vb][ab]concat=n=2:v=1:a=1[vc][ac];"
        f"[vc][1:v]overlay=0:0[vout]"
    )
    cmd = [
        FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-threads", "2",
        "-i", str(raw_mp4),
        "-i", str(overlay_png),
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-map_metadata", "-1",
        str(out_mp4),
    ]
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 50000


def _discover_from_local_iphone_db(max_clips: int = 5, specific_clip: str = "") -> list[dict]:
    """
    Doc truc tiep cac clip .mp4 tu D:\\TiktokToolerData\\recorder\\iphone_delivery.db tren Laptop.
    QUAN TRONG: Chi lay duy nhat cac clip thuoc PHIEN GHI MOI NHAT (Lần ghi này - newest session),
    tuyet doi khong lay lan sang cac phien ghi test cu truoc do!
    """
    clips = []
    seen = set()
    newest_session_tag = None

    for db_cand in [
        Path(r"D:\TiktokToolerData\recorder\iphone_delivery.db"),
        Path(r"D:\tiktok\recorder_root\iphone_delivery.db"),
    ]:
        if not db_cand.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_cand))
            cur = conn.cursor()
            cur.execute(
                "SELECT segment_id, segment_path, size_bytes, file_ready_at FROM telegram_segments ORDER BY file_ready_at DESC LIMIT 120"
            )
            for seg_id, seg_path, sz, ready_at in cur.fetchall():
                p = Path(seg_path)
                if seg_id in seen or not p.exists() or p.stat().st_size <= 50000:
                    continue
                # Xac dinh nhan phien ghi (session tag) cua clip: tiktok_live_YYYYMMDD_HHMMSS hoac thu muc job
                m_sess = re.match(r"(tiktok_live_\d{8}_\d{6})_", p.name)
                sess_tag = m_sess.group(1) if m_sess else str(p.parent)

                if not specific_clip:
                    if newest_session_tag is None:
                        newest_session_tag = sess_tag
                    elif sess_tag != newest_session_tag:
                        # Bo qua toan bo cac phien ghi cu truoc do!
                        continue

                seen.add(seg_id)
                entry = {
                    "clip_id": seg_id,
                    "url": p.as_uri(),
                    "local_path": str(p),
                    "name": p.name,
                    "session_tag": sess_tag,
                }
                if specific_clip and (specific_clip in seg_id or specific_clip in p.name):
                    clips.insert(0, entry)
                else:
                    clips.append(entry)
            conn.close()
        except Exception:
            pass
    if specific_clip:
        exact = [c for c in clips if specific_clip in c["clip_id"] or specific_clip in c.get("name", "")]
        if exact:
            return exact[:max_clips]
    return clips[:max_clips]


def discover_clips_from_livevault_link(livevault_url: str, max_clips: int = 5) -> list[dict]:
    """
    Ho tro 3 loai link thu:
    1. 'AUTO' hoac 'LOCAL': Lay truc tiep phien ghi moi nhat trong D:\\TiktokToolerData\\recorder\\iphone_delivery.db
    2. Link LiveVault (/d/<token> hoac ?session=...&clip=<sha256>): Goi JSON API /d/<token>/clips?limit=60 + anh xa file local
    3. Link TikTok Live truc tiep (https://www.tiktok.com/@.../live): Goi record_live thu clip 60s roi lay clip moi nhat
    """
    raw_input = (livevault_url or "").strip()
    if not raw_input or raw_input.upper() in ("AUTO", "LOCAL", "LATEST"):
        return _discover_from_local_iphone_db(max_clips=max_clips)

    # Neu nguoi dung dan link TikTok Live truc tiep (vd: https://www.tiktok.com/@.../live)
    if "tiktok.com/" in raw_input.lower() or raw_input.startswith("@"):
        set_editor_progress(f"🔴 Đang kết nối và thu trực tiếp Livestream TikTok ({raw_input})...", 10)
        luu_dir = Path(r"D:\tiktok\Tiktok_Tooler\Luu")
        out_root = Path(r"D:\TiktokToolerData\recorder")
        if luu_dir.exists():
            try:
                # Thu 1 doan 60s (hoac theo max_clips) bang record_live.py
                cmd = [
                    "py", "-3.12", "-c",
                    (
                        "import sys; sys.path.insert(0, r'D:\\tiktok\\Tiktok_Tooler\\Luu'); "
                        "import record_live; "
                        f"record_live.run_with_config_overrides(stream_url={json.dumps(raw_input)}, "
                        "output_dir=r'D:\\TiktokToolerData\\recorder', segment_minutes=1, segment_duration_seconds=60, "
                        "max_retries=2, telegram_enabled=False)"
                    ),
                ]
                proc = subprocess.Popen(cmd, cwd=str(luu_dir))
                # Doi cho den khi co file .mp4 moi duoc tao hoac toi da 75s * max_clips
                wait_limit = min(150, 75 * max(1, min(max_clips, 2)))
                t0 = time.time()
                while time.time() - t0 < wait_limit:
                    if proc.poll() is not None:
                        break
                    time.sleep(3)
                try:
                    proc.terminate()
                except Exception:
                    pass
            except Exception:
                pass
        # Quet file .mp4 moi nhat trong D:\TiktokToolerData\recorder
        if out_root.exists():
            mp4s = sorted(
                [p for p in out_root.rglob("*.mp4") if p.stat().st_size > 100000 and "tmp" not in str(p).lower()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            import hashlib
            res = []
            for p in mp4s[:max_clips]:
                cid = hashlib.sha256(str(p).encode("utf-8")).hexdigest()
                res.append({"clip_id": cid, "url": p.as_uri(), "local_path": str(p), "name": p.name})
            if res:
                return res

    norm_url = normalize_livevault_url(raw_input)
    parsed = urllib.parse.urlparse(norm_url)
    qs = urllib.parse.parse_qs(parsed.query)
    specific_clip = qs.get("clip", [""])[0]
    specific_session = qs.get("session", [""])[0]

    clips = []
    seen = set()

    # 1. Neu link co dang /d/<token>, goi truc tiep JSON API /d/<token>/clips?limit=60 cua LiveVault PhoneServer!
    m_tok = re.search(r"(/d/[A-Za-z0-9_-]+)", parsed.path)
    if m_tok:
        token_prefix = f"{parsed.scheme}://{parsed.netloc}{m_tok.group(1)}/"
        api_qs = ["limit=60"]
        if specific_session:
            api_qs.append(f"session={urllib.parse.quote(specific_session)}")
        if specific_clip:
            api_qs.append(f"clip={urllib.parse.quote(specific_clip)}")
        clips_api_url = f"{token_prefix}clips?{'&'.join(api_qs)}"
        try:
            raw_json = urllib.request.urlopen(clips_api_url, timeout=8).read().decode("utf-8", errors="replace")
            page_data = json.loads(raw_json)
            # Map local paths from iphone_delivery.db for instant 0.05s copy if available
            local_map = {c["clip_id"]: c.get("local_path") for c in _discover_from_local_iphone_db(max_clips=80)}
            for cobj in page_data.get("clips", []):
                cid = cobj.get("id", "")
                if cid and cid not in seen:
                    seen.add(cid)
                    entry = {
                        "clip_id": cid,
                        "url": f"{token_prefix}file/{cid}.mp4",
                        "local_path": local_map.get(cid),
                        "name": cobj.get("name", f"{cid[:10]}.mp4"),
                    }
                    if specific_clip and cid == specific_clip:
                        clips.insert(0, entry)
                    else:
                        clips.append(entry)
        except Exception:
            pass

    # 2. Neu JSON API /clips da tra ve danh sach clip -> Dung ngay!
    if clips:
        if specific_clip:
            exact = [c for c in clips if specific_clip in c["clip_id"]]
            if exact and max_clips == 1:
                return exact[:1]
        return clips[:max_clips]

    # 3. Fallback: Quet HTML hoac doc truc tiep tu iphone_delivery.db tren dia cung Laptop
    try:
        base_dir_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/"
        html = urllib.request.urlopen(norm_url, timeout=8).read().decode("utf-8", errors="replace")
        for m in re.finditer(r'href=["\']([^"\']*(?:clip=|/clip/|/download/|/file/|\.mp4)[^"\']*)["\']', html, re.I):
            href = m.group(1)
            full_href = urllib.parse.urljoin(base_dir_url, href)
            hm = re.search(r"([a-f0-9]{32,64})", full_href)
            cid = hm.group(1) if hm else Path(urllib.parse.urlparse(full_href).path).stem
            if cid and cid not in seen:
                seen.add(cid)
                clips.append({"clip_id": cid, "url": full_href})
    except Exception:
        pass

    if not clips:
        return _discover_from_local_iphone_db(max_clips=max_clips, specific_clip=specific_clip)

    return clips[:max_clips]


def start_batch_fetch_and_edit(livevault_url: str, max_clips: int = 5, forced_product_key: str = "AUTO", auto_push_first_draft: bool = True) -> dict:
    if EDITOR_STATUS["is_running"]:
        return {"ok": False, "message": "Hệ thống đang xử lý cắt & edit một loạt video khác, vui lòng đợi hoàn tất!"}

    livevault_url = (livevault_url or "").strip() or "AUTO"

    def _worker():
        import shutil
        EDITOR_STATUS["is_running"] = True
        EDITOR_STATUS["last_link"] = livevault_url
        EDITOR_STATUS["processed_clips"] = 0
        EDITOR_STATUS["created_videos"] = 0
        try:
            set_editor_progress(
                f"🔍 Bước 1/5: Đang kết nối nguồn thu ({'Phiên ghi mới nhất trong máy' if livevault_url.upper()=='AUTO' else normalize_livevault_url(livevault_url)[:55]})...",
                8,
            )
            clips = discover_clips_from_livevault_link(livevault_url, max_clips=max_clips)
            if not clips:
                set_editor_progress("⚠️ Không tìm thấy file video (.mp4) nào trong link vừa dán. Hãy kiểm tra lại link thu (/d/...).", 0)
                EDITOR_STATUS["is_running"] = False
                return

            init_db()
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT clip_id FROM posted_history")
            posted_clips = {r[0] for r in cur.fetchall()}
            conn.close()

            fresh_clips = [c for c in clips if c["clip_id"] not in posted_clips]
            EDITOR_STATUS["total_clips"] = len(fresh_clips)
            if not fresh_clips:
                set_editor_progress(
                    f"🛡️ Cả {len(clips)} clip trong link này đều ĐÃ ĐƯỢC ĐĂNG hoặc LƯU NHÁP trước đây (Chặn trùng lặp 100%)!",
                    100,
                )
                EDITOR_STATUS["is_running"] = False
                return

            new_queue_items = []
            total_f = len(fresh_clips)
            for idx, cinfo in enumerate(fresh_clips, 1):
                cid = cinfo["clip_id"]
                short_id = cid[:10]
                base_pct = int(10 + ((idx - 1) / total_f) * 75)
                set_editor_progress(
                    f"📥 Bước 2/5 [{idx}/{total_f}]: Đang lấy clip gốc {cinfo.get('name', short_id)}...",
                    base_pct + 4,
                )

                raw_mp4 = RAW_TMP_DIR / f"raw_{short_id}.mp4"
                local_src = cinfo.get("local_path")
                if local_src and Path(local_src).exists() and Path(local_src).stat().st_size > 50000:
                    shutil.copy2(local_src, str(raw_mp4))
                else:
                    dl_url = cinfo["url"]
                    if "?clip=" in dl_url and not dl_url.lower().endswith(".mp4"):
                        sub_html = urllib.request.urlopen(dl_url, timeout=10).read().decode("utf-8", errors="replace")
                        sm = re.search(r'<video[^>]+src=["\']([^"\']+)["\']|<source[^>]+src=["\']([^"\']+)["\']|href=["\']([^"\']*\.mp4[^"\']*)["\']', sub_html, re.I)
                        if sm:
                            rel = sm.group(1) or sm.group(2) or sm.group(3)
                            dl_url = urllib.parse.urljoin(dl_url, rel)
                    urllib.request.urlretrieve(dl_url, str(raw_mp4))

                if not raw_mp4.exists() or raw_mp4.stat().st_size < 50000:
                    continue

                set_editor_progress(
                    f"🎙️ Bước 3/5 [{idx}/{total_f}]: AI đang nghe lời thoại Bác Chường (8 sản phẩm) & cắt đoạn cuối vi phạm ({short_id})...",
                    base_pct + 10,
                )
                pkey, tr_text, safe_end = transcribe_and_detect_product(raw_mp4, forced_product_key=forced_product_key)
                pcat = PRODUCT_CATALOG[pkey]

                ts_tag = datetime.now().strftime("%H%M%S")
                for ch_idx, ch in enumerate(ALLOWED_CHANNELS):
                    ch_slug = ch.lstrip("@").replace(".", "_")
                    vinfo = pcat["variants"][ch]
                    overlay_png = RAW_TMP_DIR / f"pill_{short_id}_{ch_slug}.png"
                    create_yellow_pill_overlay_png(vinfo["cover_lines"], overlay_png)

                    out_name = f"AUTO_{pkey}_{ch_slug}_{short_id}_{ts_tag}.mp4"
                    out_mp4 = CACHE_DIR / out_name
                    set_editor_progress(
                        f"🎬 Bước 4/5 [{idx}/{total_f}]: Đang cắt Hook 3.5s, xóa chữ đỏ & đóng bìa vàng '{pcat['product_name'][:32]}' cho kênh {ch}...",
                        base_pct + 14 + ch_idx * 4,
                    )
                    zoom = 1.02 if ch_idx == 0 else 1.04
                    speed = 1.00 if ch_idx == 0 else 1.02
                    hook_s = 12.0 if ch_idx == 0 else 18.0
                    ok = render_single_channel_video(
                        raw_mp4=raw_mp4,
                        overlay_png=overlay_png,
                        out_mp4=out_mp4,
                        hook_start=hook_s,
                        body_start=12.0,
                        body_end=safe_end,
                        zoom=zoom,
                        speed=speed,
                    )
                    if ok:
                        EDITOR_STATUS["created_videos"] += 1
                        new_queue_items.append({
                            "id": f"auto_{short_id}_{ch_slug}_{ts_tag}",
                            "clip_id": cid,
                            "channel": ch,
                            "product_key": pkey,
                            "product_name": f"{pcat['product_name']} (Mới cắt từ clip {short_id})",
                            "seller_id": pcat["seller_id"],
                            "seller_name": pcat["seller_name"],
                            "product_id": pcat["product_id"],
                            "scheduled_at": datetime.now().strftime("%H:%M · %d/%m/%Y"),
                            "source_video": cinfo.get("name", f"clip_{short_id}.mp4"),
                            "output_video": f"output_ready/{out_name}",
                            "local_cache_path": str(out_mp4),
                            "cached_offline": True,
                            "cover_text": "\n".join(vinfo["cover_lines"]),
                            "caption_seo": vinfo["caption_seo"],
                            "transcript": tr_text or "Đã lọc sạch âm thanh & kiểm duyệt từ cấm TPCN",
                            "status": "READY",
                        })

                try:
                    raw_mp4.unlink()
                except Exception:
                    pass
                EDITOR_STATUS["processed_clips"] = idx

            if new_queue_items:
                # THEO YEU CAU NGUOI DUNG: Chi giu va dang DUY NHAT cac clip moi tu link thu moi nhat!
                # Xoa bo toan bo cac video cu chua dang khoi hang cho va khoi video_cache de khong bao gio dang nham clip test cu.
                new_fnames = {Path(x.get("output_video", "")).name for x in new_queue_items}
                for old_mp4 in CACHE_DIR.glob("*.mp4"):
                    if old_mp4.name not in new_fnames:
                        try:
                            old_mp4.unlink()
                        except Exception:
                            pass

                LOCAL_QUEUE_FILE.write_text(json.dumps(new_queue_items, ensure_ascii=False, indent=2), encoding="utf-8")

                # Buoc 5/5: Tu dong day ngay video dau tien cua loat moi sang Oppo A57 & Luu Nhap!
                draft_note = ""
                if auto_push_first_draft:
                    try:
                        from oppo_auto_poster import auto_save_draft_on_oppo, quick_check_oppo_connected
                        oppo_st = quick_check_oppo_connected()
                        if oppo_st.get("connected"):
                            first_new = new_queue_items[0]
                            set_editor_progress(
                                f"📱 Bước 5/5: Đang tự động chuyển kênh {first_new['channel']}, đẩy video đầu tiên sang Oppo A57 & Lưu Nháp Tiếng Việt...",
                                92,
                            )
                            d_res = auto_save_draft_on_oppo(item_id=first_new["id"], channel=first_new["channel"])
                            draft_note = f" | 📱 Oppo A57: {d_res.get('message', '')}"
                        else:
                            draft_note = " | (Khi cắm Oppo A57, hệ thống sẽ tự động đẩy Lưu Nháp theo lịch 1 tiếng/video)"
                    except Exception as de:
                        draft_note = f" | Lưu ý đẩy nháp: {de}"

                set_editor_progress(
                    f"✅ HOÀN TẤT TOÀN TRÌNH! Đã cắt & đóng bìa vàng {EDITOR_STATUS['created_videos']} video mới "
                    f"(từ {EDITOR_STATUS['processed_clips']} clip gốc), đưa lên ĐẦU Lịch Đăng 1 Tiếng/Video{draft_note}",
                    100,
                )
            else:
                set_editor_progress("⚠️ Không tạo được video mới nào từ link vừa dán.", 0)
        except Exception as e:
            set_editor_progress(f"❌ Lỗi khi thu & cắt video từ link mới: {e}", 0)
        finally:
            EDITOR_STATUS["is_running"] = False

    threading.Thread(target=_worker, daemon=True).start()
    return {
        "ok": True,
        "message": "🚀 Đã bắt đầu quy trình TỰ ĐỘNG TOÀN TRÌNH: Thu clip -> AI nghe sản phẩm -> FFmpeg đóng bìa vàng 2 kênh -> Đưa lên đầu lịch -> Tự đẩy sang Oppo A57 & Lưu Nháp!",
    }


CUSTOM_PRODUCTS_FILE = DATA_DIR / "custom_products.json"


def load_custom_products() -> dict:
    if CUSTOM_PRODUCTS_FILE.exists():
        try:
            custom = json.loads(CUSTOM_PRODUCTS_FILE.read_text(encoding="utf-8"))
            PRODUCT_CATALOG.update(custom)
        except Exception:
            pass
    return PRODUCT_CATALOG


def add_custom_product(
    product_key: str,
    product_name: str,
    keywords_csv: str,
    cover_lines_text: str,
    caption_seo_text: str,
    seller_id: str = "7494727475325798000",
) -> dict:
    load_custom_products()
    pkey = re.sub(r"[^a-z0-9_]", "_", product_key.strip().lower()) or f"sp_{int(time.time())}"
    kws = [k.strip().lower() for k in keywords_csv.split(",") if k.strip()]
    clines = [ln.strip() for ln in cover_lines_text.splitlines() if ln.strip()][:4]
    if not clines:
        clines = [product_name[:24], "Chăm sóc sức khỏe chủ động", "Hàng chính hãng uy tín"]

    entry = {
        "keywords": kws,
        "product_name": product_name.strip(),
        "seller_id": seller_id.strip() or "7494727475325798000",
        "seller_name": f"Shop GMV Max ({seller_id.strip()})",
        "product_id": "1738159842879505899",
        "variants": {
            "@suckhoeviet.2": {"cover_lines": clines, "caption_seo": caption_seo_text.strip()},
            "@suc.khoe.vang.268": {"cover_lines": clines, "caption_seo": caption_seo_text.strip()},
        },
    }
    custom = {}
    if CUSTOM_PRODUCTS_FILE.exists():
        try:
            custom = json.loads(CUSTOM_PRODUCTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            custom = {}
    custom[pkey] = entry
    CUSTOM_PRODUCTS_FILE.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    PRODUCT_CATALOG[pkey] = entry
    return {"ok": True, "product_key": pkey, "message": f"✓ Đã thêm sản phẩm mới '{product_name}' vào từ điển AI nhận diện giọng nói!"}


def change_video_item_product(item_id: str, new_product_key: str) -> dict:
    """
    Doi san pham cho 1 video bi gan nham tren bang Lich Dang:
    1. Cap nhat product_name, cover_text, caption_seo, seller_id trong local_queue.json
    2. Neu file .mp4 da co trong C:\\TikTok_AutoHub\\video_cache\\, tu dong dong lai khung chu Vang chu Den moi de che chu cu 100%!
    """
    load_custom_products()
    if new_product_key not in PRODUCT_CATALOG:
        return {"ok": False, "message": f"Mã sản phẩm '{new_product_key}' không tồn tại trong danh mục."}

    if not LOCAL_QUEUE_FILE.exists():
        return {"ok": False, "message": "Không tìm thấy local_queue.json"}

    q = json.loads(LOCAL_QUEUE_FILE.read_text(encoding="utf-8"))
    target = next((x for x in q if x.get("id") == item_id), None)
    if not target:
        return {"ok": False, "message": f"Không tìm thấy video có mã {item_id}"}

    pcat = PRODUCT_CATALOG[new_product_key]
    ch = target.get("channel", "@suckhoeviet.2")
    vinfo = pcat["variants"].get(ch) or pcat["variants"]["@suckhoeviet.2"]

    target["product_key"] = new_product_key
    target["product_name"] = pcat["product_name"]
    target["seller_id"] = pcat["seller_id"]
    target["seller_name"] = pcat["seller_name"]
    target["cover_text"] = "\n".join(vinfo["cover_lines"])
    target["caption_seo"] = vinfo["caption_seo"]
    LOCAL_QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")

    # Dong lai khung chu Vang chu Den moi len file .mp4 trong video_cache (de che khung chu cu!)
    fname = Path(target.get("output_video", "")).name
    cached_mp4 = CACHE_DIR / fname
    rerendered_note = ""
    if cached_mp4.exists() and cached_mp4.stat().st_size > 50000:
        overlay_png = RAW_TMP_DIR / f"re_pill_{item_id}.png"
        # Ve hop nen vang che kin vung chu cu (y=680..930) + in 4 dong chu moi
        W, H = 720, 1280
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font_path = r"C:\Windows\Fonts\arialbd.ttf" if Path(r"C:\Windows\Fonts\arialbd.ttf").exists() else r"C:\Windows\Fonts\segoeui.ttf"
        draw.rounded_rectangle([85, 680, 635, 920], radius=18, fill=(253, 224, 71, 255), outline=(15, 23, 42, 255), width=3)
        y_cur = 696
        for idx, ln in enumerate(vinfo["cover_lines"][:4]):
            fsize = 27 if idx == 0 else 24
            font = ImageFont.truetype(font_path, fsize)
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
            while tw > 510 and fsize > 17:
                fsize -= 1
                font = ImageFont.truetype(font_path, fsize)
                bbox = draw.textbbox((0, 0), ln, font=font)
                tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y_cur), ln, font=font, fill=(10, 10, 10, 255))
            y_cur += 52
        img.save(str(overlay_png), "PNG")

        tmp_out = RAW_TMP_DIR / f"fixed_{fname}"
        cmd = [
            FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-threads", "2",
            "-i", str(cached_mp4), "-i", str(overlay_png),
            "-filter_complex", "[0:v][1:v]overlay=0:0[vout]",
            "-map", "[vout]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy",
            str(tmp_out),
        ]
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        if r.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 50000:
            tmp_out.replace(cached_mp4)
            rerendered_note = " & Đã đóng lại khung chữ bìa vàng mới đè lên video .MP4!"

    return {
        "ok": True,
        "message": f"✓ Đã đổi sản phẩm của video sang '{pcat['product_name']}', cập nhật Caption Tiếng Việt{rerendered_note}",
    }


load_custom_products()
